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

For planning details and future implementation notes, see [OTHER.md](OTHER.md).

## Dockerization Commands (AWS ECR)

### 0) Configure AWS CLI credentials (named profile)

```bash
aws configure --profile hb-raw-data-pipeline
aws configure set region us-east-1 --profile hb-raw-data-pipeline
export AWS_PROFILE=hb-raw-data-pipeline
```

### 1) Authenticate Docker to Amazon ECR

Retrieve an authentication token and authenticate your Docker client to your registry:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 317380566856.dkr.ecr.us-east-1.amazonaws.com
```

> Note: If you receive an error using the AWS CLI, make sure that you have the latest version of the AWS CLI and Docker installed.

### 2) Build the Docker image

```bash
docker build -t hb-raw-data-pipeline .
```

If your image is already built, you can skip this step.

### 3) Tag the image for ECR

```bash
docker tag hb-raw-data-pipeline:latest 317380566856.dkr.ecr.us-east-1.amazonaws.com/hb-raw-data-pipeline:latest
```

### 4) Push image to ECR

```bash
docker push 317380566856.dkr.ecr.us-east-1.amazonaws.com/hb-raw-data-pipeline:latest
```

## Production Schedule

- The production pipeline runs on a **weekly schedule**.
