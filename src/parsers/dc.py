from __future__ import annotations

from .base import ParserProbe


class DCDocumentParser:
    parser_key = "dc"
    document_type = "DC"

    def probe(self) -> ParserProbe:
        return ParserProbe(
            parser_key=self.parser_key,
            document_type=self.document_type,
            status="skeleton_ready",
            message="DC parser skeleton is available. Parsing logic will be integrated later.",
        )
