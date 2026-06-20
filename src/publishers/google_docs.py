"""
Google Docs Publisher — publishes generated documentation to Google Docs.

This module takes the generated Markdown documentation and creates (or updates)
Google Docs documents via the Google Docs API and Google Drive API.

HOW GOOGLE DOCS API WORKS (simplified):
    Unlike Confluence (which accepts HTML-like storage format), Google Docs uses
    a "batch update" model where you send a list of operations:

        POST /v1/documents/{docId}:batchUpdate
        Body: { requests: [ {insertText: ...}, {updateTextStyle: ...}, ... ] }

    The operations are applied in sequence. So to create a document with formatted
    content, you:
    1. Create an empty doc via the Drive API
    2. Insert text at the end (unformatted)
    3. Apply formatting (bold, headings, etc.) to specific text ranges

    This is more complex than Confluence's approach, but gives precise control
    over the final document's appearance.

AUTHENTICATION:
    Google APIs use OAuth2 or service accounts. For automation, service accounts
    are the way to go:
    1. Create a service account in Google Cloud Console
    2. Download the JSON key file
    3. Share your target Drive folder with the service account's email
    4. Point the config at the JSON key file

USAGE:
    from src.publishers.google_docs import GoogleDocsPublisher
    from src.config.settings import GoogleDocsConfig

    config = GoogleDocsConfig(
        credentials_file="/path/to/service-account-key.json",
        folder_id="1ABC...",  # Google Drive folder ID
    )
    publisher = GoogleDocsPublisher(config)
    result = await publisher.publish(technical_doc, non_technical_doc, repo_name="my-app")

REQUIRED PACKAGES:
    pip install google-api-python-client google-auth google-auth-httplib2
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config.settings import GoogleDocsConfig


class GoogleDocsPublisher:
    """Publishes documentation to Google Docs.

    Creates or updates Google Docs documents in a specified Google Drive folder.
    Each doc type (technical, non-technical) gets its own document.

    The publisher can operate in two modes:
    1. CREATE mode: Creates new documents each time (default)
    2. UPDATE mode: Updates specific document IDs (set technical_doc_id / non_technical_doc_id)
    """

    def __init__(self, config: GoogleDocsConfig):
        self.config = config
        self._docs_service = None
        self._drive_service = None

    def _get_services(self):
        """Lazily initialize the Google API services.

        We defer this to avoid import errors if google-api packages aren't installed.
        The imports are inside the method so the rest of the codebase works
        even without the google dependencies.
        """
        if self._docs_service is not None:
            return self._docs_service, self._drive_service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google API packages not installed. Run:\n"
                "  pip install google-api-python-client google-auth google-auth-httplib2"
            )

        # Authenticate using the service account key file
        credentials_path = Path(self.config.credentials_file)
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Google credentials file not found: {credentials_path}\n"
                "Download your service account key from Google Cloud Console:\n"
                "  IAM & Admin → Service Accounts → Keys → Add Key → JSON"
            )

        SCOPES = [
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
        ]
        creds = service_account.Credentials.from_service_account_file(
            str(credentials_path), scopes=SCOPES,
        )

        self._docs_service = build("docs", "v1", credentials=creds)
        self._drive_service = build("drive", "v3", credentials=creds)

        return self._docs_service, self._drive_service

    async def publish(
        self,
        technical_doc: str,
        non_technical_doc: str,
        repo_name: str = "Repository",
    ) -> GoogleDocsPublishResult:
        """Publish both documents to Google Docs.

        NOTE: The Google API client library is synchronous, so we run the
        actual API calls synchronously within this async method. In a production
        system, you'd use aiogoogle or run these in an executor. For our use
        case (called once per doc generation), this is perfectly fine.
        """
        result = GoogleDocsPublishResult(repo_name=repo_name)

        try:
            docs_service, drive_service = self._get_services()
        except (ImportError, FileNotFoundError) as e:
            result.error = str(e)
            return result

        # Publish technical doc
        if technical_doc:
            tech_title = f"{repo_name} — Technical Documentation"
            try:
                doc_id, doc_url = self._publish_document(
                    docs_service, drive_service,
                    title=tech_title,
                    markdown_content=technical_doc,
                    existing_doc_id=self.config.technical_doc_id,
                )
                result.technical_success = True
                result.technical_url = doc_url
                result.technical_doc_id = doc_id
            except Exception as e:
                result.technical_error = str(e)

        # Publish non-technical doc
        if non_technical_doc:
            simple_title = f"{repo_name} — Non-Technical Guide"
            try:
                doc_id, doc_url = self._publish_document(
                    docs_service, drive_service,
                    title=simple_title,
                    markdown_content=non_technical_doc,
                    existing_doc_id=self.config.non_technical_doc_id,
                )
                result.non_technical_success = True
                result.non_technical_url = doc_url
                result.non_technical_doc_id = doc_id
            except Exception as e:
                result.non_technical_error = str(e)

        return result

    def _publish_document(
        self,
        docs_service,
        drive_service,
        title: str,
        markdown_content: str,
        existing_doc_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """Create or update a single Google Doc with the given content.

        Returns a tuple of (document_id, document_url).
        """
        if existing_doc_id:
            # UPDATE mode: clear existing content and replace it
            doc_id = existing_doc_id
            self._clear_document(docs_service, doc_id)
        else:
            # CREATE mode: create a new document
            doc_id = self._create_document(docs_service, drive_service, title)

        # Parse markdown into structured content blocks
        blocks = self._parse_markdown_to_blocks(markdown_content)

        # Build the batch update requests
        requests = self._blocks_to_requests(blocks)

        # Execute the batch update
        if requests:
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        return doc_id, doc_url

    def _create_document(self, docs_service, drive_service, title: str) -> str:
        """Create a new empty Google Doc and optionally move it to the target folder."""
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        # Move to the target folder if configured
        if self.config.folder_id:
            # Get the file's current parent to remove it from there
            file_info = drive_service.files().get(
                fileId=doc_id, fields="parents",
            ).execute()
            previous_parents = ",".join(file_info.get("parents", []))

            drive_service.files().update(
                fileId=doc_id,
                addParents=self.config.folder_id,
                removeParents=previous_parents,
                fields="id, parents",
            ).execute()

        return doc_id

    def _clear_document(self, docs_service, doc_id: str) -> None:
        """Clear all content from an existing document for replacement.

        Google Docs doesn't have a "replace all content" operation. Instead,
        we need to delete everything and then insert the new content.
        """
        doc = docs_service.documents().get(documentId=doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        if len(content) <= 1:
            return  # Document is already empty

        # Calculate the range to delete (from index 1 to end - 1)
        # Index 0 is always the document's section break; content starts at 1
        end_index = content[-1].get("endIndex", 1) - 1
        if end_index <= 1:
            return

        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [{
                    "deleteContentRange": {
                        "range": {"startIndex": 1, "endIndex": end_index}
                    }
                }]
            },
        ).execute()

    def _parse_markdown_to_blocks(self, markdown: str) -> list[dict]:
        """Parse markdown into a list of structured content blocks.

        Each block is a dict with:
        - type: "heading1", "heading2", "heading3", "paragraph", "code", "list_item"
        - text: the raw text content
        - bold_ranges: list of (start, end) tuples for bold text
        - code_ranges: list of (start, end) tuples for inline code
        """
        blocks = []
        lines = markdown.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Code blocks
            if line.startswith("```"):
                language = line[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                blocks.append({
                    "type": "code",
                    "text": "\n".join(code_lines),
                    "language": language,
                })
                continue

            # Headings
            if line.startswith("# "):
                blocks.append({"type": "heading1", "text": line[2:].strip()})
            elif line.startswith("## "):
                blocks.append({"type": "heading2", "text": line[3:].strip()})
            elif line.startswith("### "):
                blocks.append({"type": "heading3", "text": line[4:].strip()})
            # List items
            elif line.startswith("- "):
                blocks.append({"type": "list_item", "text": line[2:].strip()})
            # Horizontal rule
            elif line.strip() == "---":
                blocks.append({"type": "hr", "text": ""})
            # Blockquote
            elif line.startswith("> "):
                blocks.append({"type": "blockquote", "text": line[2:].strip()})
            # Regular paragraph (skip empty lines)
            elif line.strip():
                blocks.append({"type": "paragraph", "text": line.strip()})

            i += 1

        return blocks

    def _blocks_to_requests(self, blocks: list[dict]) -> list[dict]:
        """Convert parsed content blocks into Google Docs API batchUpdate requests.

        Google Docs API works by inserting text at specific indices, then
        applying formatting to text ranges. We build the document from
        bottom to top (inserting at index 1 each time) to avoid having to
        track shifting indices.

        Actually, the standard approach is to insert all text first (tracking
        the current end index), then apply formatting. We'll do it in two passes:
        Pass 1: Insert all text at index 1, building up the document
        Pass 2: Apply formatting (headings, bold, code style) to the ranges
        """
        requests = []
        # We track the current insertion point — everything goes at index 1
        # (right after the document's initial section break)
        insert_index = 1

        # Formatting requests to apply after all text is inserted
        format_requests = []

        for block in blocks:
            block_type = block["type"]
            text = block.get("text", "")

            if block_type == "hr":
                # Insert a horizontal line (using repeated dashes as a visual separator)
                insert_text = "━" * 50 + "\n"
                requests.append({
                    "insertText": {
                        "location": {"index": insert_index},
                        "text": insert_text,
                    }
                })
                # Style the separator line
                format_requests.append({
                    "updateTextStyle": {
                        "range": {
                            "startIndex": insert_index,
                            "endIndex": insert_index + len(insert_text) - 1,
                        },
                        "textStyle": {
                            "foregroundColor": {
                                "color": {"rgbColor": {"red": 0.7, "green": 0.7, "blue": 0.7}}
                            },
                            "fontSize": {"magnitude": 8, "unit": "PT"},
                        },
                        "fields": "foregroundColor,fontSize",
                    }
                })
                insert_index += len(insert_text)
                continue

            if block_type == "code":
                # Insert code as a paragraph with monospace styling
                code_text = text + "\n\n"
                requests.append({
                    "insertText": {
                        "location": {"index": insert_index},
                        "text": code_text,
                    }
                })
                # Apply monospace font to code blocks
                format_requests.append({
                    "updateTextStyle": {
                        "range": {
                            "startIndex": insert_index,
                            "endIndex": insert_index + len(code_text) - 1,
                        },
                        "textStyle": {
                            "weightedFontFamily": {"fontFamily": "Courier New"},
                            "fontSize": {"magnitude": 9, "unit": "PT"},
                            "backgroundColor": {
                                "color": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}}
                            },
                        },
                        "fields": "weightedFontFamily,fontSize,backgroundColor",
                    }
                })
                insert_index += len(code_text)
                continue

            # Strip markdown formatting from text for insertion
            clean_text = self._strip_markdown_formatting(text)
            insert_text = clean_text + "\n"

            if block_type == "list_item":
                insert_text = "  •  " + clean_text + "\n"

            if block_type == "blockquote":
                insert_text = "    │ " + clean_text + "\n"

            requests.append({
                "insertText": {
                    "location": {"index": insert_index},
                    "text": insert_text,
                }
            })

            # Apply heading styles
            heading_styles = {
                "heading1": "HEADING_1",
                "heading2": "HEADING_2",
                "heading3": "HEADING_3",
            }

            if block_type in heading_styles:
                format_requests.append({
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": insert_index,
                            "endIndex": insert_index + len(insert_text),
                        },
                        "paragraphStyle": {
                            "namedStyleType": heading_styles[block_type],
                        },
                        "fields": "namedStyleType",
                    }
                })

            # Detect bold ranges (**text**) in original text and apply bold styling
            bold_ranges = self._find_bold_ranges(text, insert_index)
            for start, end in bold_ranges:
                format_requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                })

            insert_index += len(insert_text)

        # Combine: first insert all text, then apply all formatting
        return requests + format_requests

    def _strip_markdown_formatting(self, text: str) -> str:
        """Remove markdown syntax while preserving the plain text."""
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)       # italic
        text = re.sub(r'_(.+?)_', r'\1', text)          # italic
        text = re.sub(r'`(.+?)`', r'\1', text)          # inline code
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links
        return text

    def _find_bold_ranges(
        self, original_text: str, base_index: int,
    ) -> list[tuple[int, int]]:
        """Find the positions of bold text in the original markdown.

        This is tricky because we need to map positions in the markdown
        (with ** markers) to positions in the cleaned text (without ** markers).
        We do a simple approach: find **text** patterns and calculate their
        position in the stripped version.
        """
        ranges = []
        # Simple approach: find bold patterns in the stripped text
        stripped = self._strip_markdown_formatting(original_text)
        for match in re.finditer(r'\*\*(.+?)\*\*', original_text):
            bold_text = match.group(1)
            # Find this text in the stripped version
            pos = stripped.find(bold_text)
            if pos >= 0:
                ranges.append((
                    base_index + pos,
                    base_index + pos + len(bold_text),
                ))
        return ranges


class GoogleDocsPublishResult:
    """Result of a Google Docs publish operation."""

    def __init__(self, repo_name: str = ""):
        self.repo_name = repo_name
        self.technical_success = False
        self.technical_url = ""
        self.technical_doc_id = ""
        self.technical_error = ""
        self.non_technical_success = False
        self.non_technical_url = ""
        self.non_technical_doc_id = ""
        self.non_technical_error = ""
        self.error = ""
        self.timestamp = datetime.utcnow().isoformat()

    @property
    def all_success(self) -> bool:
        return self.technical_success and self.non_technical_success and not self.error

    def summary(self) -> str:
        lines = [f"Google Docs Publish — {self.repo_name}"]
        if self.error:
            lines.append(f"  ❌ Error: {self.error}")
            return "\n".join(lines)
        if self.technical_success:
            lines.append(f"  ✅ Technical Doc: {self.technical_url}")
        elif self.technical_error:
            lines.append(f"  ❌ Technical Doc: {self.technical_error}")
        if self.non_technical_success:
            lines.append(f"  ✅ Non-Technical Guide: {self.non_technical_url}")
        elif self.non_technical_error:
            lines.append(f"  ❌ Non-Technical Guide: {self.non_technical_error}")
        return "\n".join(lines)
