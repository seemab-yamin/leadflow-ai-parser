from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentTypeDefinition:
    code: str
    folder_aliases: tuple[str, ...]
    parser_key: str
    integration_status: str
    description: str


# Source of truth for document formats currently supported by the pipeline.
# Add new document types here as new folders/parsers become available.
DOCUMENT_TYPE_CATALOG: dict[str, DocumentTypeDefinition] = {
    "DC": DocumentTypeDefinition(
        code="DC",
        folder_aliases=("DC",),
        parser_key="dc",
        integration_status="ready_for_integration",
        description="DC document parser skeleton is prepared.",
    ),
}


def resolve_document_type(folder_name: str) -> DocumentTypeDefinition | None:
    normalized = folder_name.strip().upper()
    for definition in DOCUMENT_TYPE_CATALOG.values():
        if normalized in definition.folder_aliases:
            return definition
    return None
