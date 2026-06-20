"""
Confluence Publisher — publishes generated documentation to Atlassian Confluence.

This module takes the generated Markdown documentation and publishes it as
Confluence pages in a specified space. It handles:

1. Converting Markdown to Confluence's storage format (XHTML-based)
2. Creating new pages or updating existing ones
3. Organizing pages under a parent page (optional)
4. Preserving Mermaid diagrams as code blocks with a note

HOW CONFLUENCE'S API WORKS (simplified):
    Confluence stores page content in "storage format" — a subset of XHTML
    with Confluence-specific macros. You can't just push raw Markdown or HTML;
    it needs to be in their specific format.

    To create a page:
        POST /rest/api/content
        Body: { type, title, space, body: { storage: { value, representation } } }

    To update a page:
        PUT /rest/api/content/{id}
        Body: same as create, but with version number incremented

    Authentication: Basic auth with email + API token (NOT password).
    The API token is generated from id.atlassian.com/manage-profile/security/api-tokens.

USAGE:
    from src.publishers.confluence import ConfluencePublisher
    from src.config.settings import ConfluenceConfig

    config = ConfluenceConfig(
        url="https://yourcompany.atlassian.net",
        email="you@company.com",
        api_token="your-api-token",
        space_key="ENG",
    )
    publisher = ConfluencePublisher(config)

    # Publish both docs
    result = await publisher.publish(technical_doc, non_technical_doc, repo_name="my-app")
"""

from __future__ import annotations

import re
import ssl
from datetime import datetime
from typing import Optional

import httpx

try:
    import truststore
    _ssl_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:
    _ssl_ctx = True

from src.config.settings import ConfluenceConfig


class ConfluencePublisher:
    """Publishes documentation to Confluence.

    Each documentation type (technical + non-technical) becomes its own
    Confluence page. If a parent_page_id is configured, both pages are
    created as children of that page, keeping things organized.

    On subsequent runs, the publisher finds existing pages with the same
    title and UPDATES them (incrementing the version number) rather than
    creating duplicates. This means your docs always stay current at the
    same URL.
    """

    def __init__(self, config: ConfluenceConfig):
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.api_url = f"{self.base_url}/wiki/rest/api"

        # Confluence uses Basic auth: base64(email:api_token)
        self.auth = (config.email, config.api_token)

    async def publish(
        self,
        technical_doc: str,
        non_technical_doc: str,
        repo_name: str = "Repository",
    ) -> PublishResult:
        """Publish both documents to Confluence.

        Creates or updates two pages:
        - "{repo_name} — Technical Documentation"
        - "{repo_name} — Non-Technical Guide"

        Returns a PublishResult with URLs to both pages.
        """
        results = PublishResult(repo_name=repo_name)

        async with httpx.AsyncClient(timeout=60.0, verify=_ssl_ctx) as client:
            # Publish technical doc
            if technical_doc:
                tech_title = f"{repo_name} — Technical Documentation"
                tech_content = self._markdown_to_confluence(technical_doc)

                tech_result = await self._create_or_update_page(
                    client, tech_title, tech_content,
                )
                results.technical_url = tech_result.get("url", "")
                results.technical_page_id = tech_result.get("id", "")
                results.technical_success = tech_result.get("success", False)

            # Publish non-technical doc
            if non_technical_doc:
                simple_title = f"{repo_name} — Non-Technical Guide"
                simple_content = self._markdown_to_confluence(non_technical_doc)

                simple_result = await self._create_or_update_page(
                    client, simple_title, simple_content,
                )
                results.non_technical_url = simple_result.get("url", "")
                results.non_technical_page_id = simple_result.get("id", "")
                results.non_technical_success = simple_result.get("success", False)

        return results

    async def _create_or_update_page(
        self,
        client: httpx.AsyncClient,
        title: str,
        content: str,
    ) -> dict:
        """Create a new Confluence page or update an existing one.

        The logic is:
        1. Search for an existing page with this exact title in the space
        2. If found: update it (increment version number)
        3. If not found: create a new page

        This makes the publisher idempotent — running it twice doesn't create
        duplicate pages.
        """
        try:
            # Step 1: Check if the page already exists
            existing = await self._find_page_by_title(client, title)

            if existing and self.config.update_existing:
                # Step 2a: Update existing page
                page_id = existing["id"]
                current_version = existing["version"]["number"]

                update_data = {
                    "id": page_id,
                    "type": "page",
                    "title": title,
                    "space": {"key": self.config.space_key},
                    "body": {
                        "storage": {
                            "value": content,
                            "representation": "storage",
                        }
                    },
                    "version": {"number": current_version + 1},
                }

                response = await client.put(
                    f"{self.api_url}/content/{page_id}",
                    json=update_data,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                page_url = f"{self.base_url}/wiki{data['_links']['webui']}"
                return {"success": True, "id": page_id, "url": page_url, "action": "updated"}

            else:
                # Step 2b: Create new page
                create_data = {
                    "type": "page",
                    "title": title,
                    "space": {"key": self.config.space_key},
                    "body": {
                        "storage": {
                            "value": content,
                            "representation": "storage",
                        }
                    },
                }

                # Nest under parent page if configured
                if self.config.parent_page_id:
                    create_data["ancestors"] = [{"id": self.config.parent_page_id}]

                response = await client.post(
                    f"{self.api_url}/content",
                    json=create_data,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                page_url = f"{self.base_url}/wiki{data['_links']['webui']}"
                return {"success": True, "id": data["id"], "url": page_url, "action": "created"}

        except httpx.HTTPStatusError as e:
            error_body = e.response.text[:500] if e.response else "No response body"
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {error_body}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _find_page_by_title(
        self, client: httpx.AsyncClient, title: str,
    ) -> Optional[dict]:
        """Search for an existing page by title in the configured space.

        Uses direct space content listing instead of CQL because CQL ignores
        the space filter for personal spaces (keys starting with ~).
        """
        try:
            response = await client.get(
                f"{self.api_url}/space/{self.config.space_key}/content/page",
                params={"expand": "version", "limit": 100},
                auth=self.auth,
            )
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                if result.get("title") == title:
                    return result
            return None

        except Exception:
            return None

    def _markdown_to_confluence(self, markdown: str) -> str:
        """Convert Markdown to Confluence storage format (XHTML)."""
        html = markdown

        # Extract code blocks first, replace with placeholders to protect
        # their content from being wrapped in <p> tags later
        code_blocks: list[str] = []

        def _stash_mermaid(m):
            code_blocks.append(self._mermaid_to_confluence_macro(m.group(1)))
            return f'\x00CODEBLOCK{len(code_blocks) - 1}\x00'

        def _stash_code(m):
            code_blocks.append(self._code_to_confluence_macro(m.group(2), m.group(1)))
            return f'\x00CODEBLOCK{len(code_blocks) - 1}\x00'

        html = re.sub(r'```mermaid\n(.*?)```', _stash_mermaid, html, flags=re.DOTALL)
        html = re.sub(r'```(\w*)\n(.*?)```', _stash_code, html, flags=re.DOTALL)

        # Convert inline code
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

        # Convert headings (process largest first to avoid ## matching # first)
        html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Bold and italic (skip underscore italic — too risky with code content
        # containing function_names_with_underscores)
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

        # Blockquotes
        html = re.sub(r'^> (.+)$', r'<blockquote><p>\1</p></blockquote>', html, flags=re.MULTILINE)

        # Unordered lists
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.*?</li>\n?)+', r'<ul>\g<0></ul>', html)

        # Horizontal rules
        html = re.sub(r'^---$', '<hr />', html, flags=re.MULTILINE)

        # Wrap remaining plain text lines in <p> tags
        lines = html.split('\n')
        result = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('<') and not stripped.startswith('\x00'):
                result.append(f'<p>{stripped}</p>')
            else:
                result.append(line)
        html = '\n'.join(result)

        # Restore code blocks from placeholders
        for i, block in enumerate(code_blocks):
            html = html.replace(f'\x00CODEBLOCK{i}\x00', block)

        return html

    def _code_to_confluence_macro(self, code: str, language: str = "") -> str:
        """Convert a code block to a simple HTML pre/code block."""
        escaped_code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f'<pre><code>{escaped_code}</code></pre>'

    def _mermaid_to_confluence_macro(self, mermaid_code: str) -> str:
        """Convert a Mermaid diagram to a blockquote with the raw code."""
        escaped = mermaid_code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return (
            f'<blockquote>'
            f'<p><strong>Architecture Diagram (Mermaid)</strong></p>'
            f'<p>Copy this code to <a href="https://mermaid.live">mermaid.live</a> to view the diagram:</p>'
            f'<pre><code>{escaped}</code></pre>'
            f'</blockquote>'
        )


class PublishResult:
    """Result of a Confluence publish operation."""

    def __init__(self, repo_name: str = ""):
        self.repo_name = repo_name
        self.technical_success = False
        self.technical_url = ""
        self.technical_page_id = ""
        self.non_technical_success = False
        self.non_technical_url = ""
        self.non_technical_page_id = ""
        self.timestamp = datetime.utcnow().isoformat()

    @property
    def all_success(self) -> bool:
        return self.technical_success and self.non_technical_success

    def summary(self) -> str:
        lines = [f"Confluence Publish — {self.repo_name}"]
        if self.technical_success:
            lines.append(f"  ✅ Technical Doc: {self.technical_url}")
        else:
            lines.append(f"  ❌ Technical Doc: failed")
        if self.non_technical_success:
            lines.append(f"  ✅ Non-Technical Guide: {self.non_technical_url}")
        else:
            lines.append(f"  ❌ Non-Technical Guide: failed")
        return "\n".join(lines)
