"""Publishers — push generated documentation to external platforms."""

from src.publishers.confluence import ConfluencePublisher
from src.publishers.google_docs import GoogleDocsPublisher

__all__ = ["ConfluencePublisher", "GoogleDocsPublisher"]
