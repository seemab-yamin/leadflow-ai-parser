# HB Raw Data Pipeline

A data pipeline for processing raw PDF files from Google Drive, identifying the document type by folder name, extracting the relevant data, and saving the parsed result to Google Sheets.

## Overview

This project is designed to be a small but robust pipeline that can grow over time. The architecture is intentionally simple so new document types can be added without rewriting the whole project.

## Current Flow

1. PDFs are stored in Google Drive.
2. The pipeline reads files from folders that represent document types.
3. Each document type is processed by its own parser.
4. Extracted data is transformed into a tabular format.
5. The results are written to Google Sheets.

## Document Type Strategy

Document types are identified by folder name. This makes it easy to add support for new formats later:

- create a new folder for the document type in Google Drive
- add a matching parser in the codebase
- map the folder name to the parser
- reuse the same pipeline flow and output format

## Suggested Repository Structure

```text
hb-raw-data-pipeline/
├── src/
│   ├── config/
│   ├── connectors/
│   ├── parsers/
│   ├── services/
│   ├── transforms/
│   └── main.py
├── tests/
├── docs/
└── README.md
```

### Purpose of Each Area

- `config/`: environment settings, credentials, and pipeline configuration
- `connectors/`: Google Drive and Google Sheets integration
- `parsers/`: one parser per document type
- `services/`: orchestration and shared business logic
- `transforms/`: normalization and data shaping
- `tests/`: unit and integration tests
- `docs/`: project notes and document type specs

## Design Goals

- keep parsers isolated by document type
- make it easy to add new document types later
- keep Google API integration separate from parsing logic
- support reuse of the same structure in future projects

## Next Steps

- define the first supported document type
- add the initial parser and Google integrations
- document the expected output schema for Google Sheets
- add tests for parsing and data mapping

## Notes

This repository currently contains only documentation. The implementation can be added incrementally following the structure above.
