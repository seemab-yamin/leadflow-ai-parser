from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ParserProbe:
    parser_key: str
    document_type: str
    status: str
    message: str


class DocumentParser(Protocol):
    parser_key: str
    document_type: str

    def probe(self) -> ParserProbe:
        ...
