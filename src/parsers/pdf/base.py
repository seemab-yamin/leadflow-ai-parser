from __future__ import annotations

from abc import ABC, abstractmethod


class PDFParser(ABC):
    """Abstract contract for PDF text extraction implementations."""

    @abstractmethod
    def extract_text(self, content: bytes) -> str:
        """Extract plain text from raw PDF bytes."""
        raise NotImplementedError
