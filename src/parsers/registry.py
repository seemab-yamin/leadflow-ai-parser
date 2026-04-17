from __future__ import annotations

from .base import DocumentParser
from .dc import DCDocumentParser


PARSER_REGISTRY: dict[str, DocumentParser] = {
    "dc": DCDocumentParser(),
}


def get_parser(parser_key: str) -> DocumentParser | None:
    return PARSER_REGISTRY.get(parser_key)
