"""Normalise PDF, HTML, Confluence pages, database rows, and tickets into text."""

from __future__ import annotations

import base64
import json
import re
from html.parser import HTMLParser

from knowledge_assistant.platform import AppError


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip = True
        if tag in {"p", "h1", "h2", "li", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def normalise(media_type: str, content: str) -> str:
    if media_type in {"text/plain", "text/markdown"}:
        return content.strip()
    if media_type == "text/html":
        parser = _HTMLText()
        parser.feed(content)
        return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()
    if media_type == "application/pdf":
        return _pdf(content)
    if media_type == "application/x-confluence":
        page = json.loads(content)
        return f"# {page['title']}\n{page['body']}".strip()
    if media_type == "application/x-database-row":
        row = json.loads(content)
        columns = "\n".join(f"{key}: {value}" for key, value in row["columns"].items())
        return f"# {row['table']} {row['primaryKey']}\n{columns}"
    if media_type == "application/x-ticket":
        ticket = json.loads(content)
        return f"# {ticket['id']}\n{ticket['summary']}\n{ticket.get('description', '')}".strip()
    raise AppError(415, "Unsupported media type", "This source type is not ingested.", "unsupported-media")


def _pdf(content: str) -> str:
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except ImportError as exc:
        raise AppError(500, "PDF parser missing", "Install pypdf to ingest PDF documents.", "pdf-parser-missing") from exc
    try:
        payload = base64.b64decode(content, validate=True)
    except Exception as exc:
        raise AppError(422, "Invalid PDF", "PDF content must be base64.", "invalid-pdf") from exc
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(payload)).pages).strip()
    if not text:
        raise AppError(422, "Empty PDF", "No text could be extracted from the PDF.", "empty-pdf")
    return text
