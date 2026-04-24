# HB Raw Data Pipeline

A data pipeline for processing raw PDF files from Google Drive, identifying the document type by folder name, extracting the relevant data, and saving the parsed result to Google Sheets.

## Pipeline Diagram

```text
Google Drive → Publisher (Lambda) → SQS → Consumer (Lambda) → Processed → Move File
			  ↑                              ↓
		  Killswitch                    LLM + Pre/Post Processing
```

### Flow Summary

- Google Drive stores the source files.
- The Publisher Lambda discovers eligible document type folders and publishes file metadata to SQS.
- The Consumer Lambda receives SQS messages, fetches file content, and processes the document.
- Processed files are moved after successful handling.
- A killswitch can stop the pipeline when needed.
- LLM + pre/post-processing happens inside the consumer flow.

## Publisher Deployment Notes

The publisher implementation is complete and ready for Lambda deployment, with these important checks:

- `ENABLED_FOLDERS` must contain the **immediate child folder names** under the configured `GOOGLE_DRIVE_FOLDER_ID` root.
- `ENABLED_FOLDERS` is read as JSON, for example `[
	"DC"
]`.
- Folder enablement is case-insensitive and trimmed, so `DC`, `dc`, and ` DC ` are treated the same.
- Only enabled document type folders are crawled for files.
- SQS batch publishing is limited to a maximum of 10 messages per batch.
- **Reliability**: The SQS queue should be configured with a **Dead-Letter Queue (DLQ)** to capture messages that fail processing after multiple retries (e.g., `maxReceiveCount: 3`).
- The consumer can fetch file content using the Drive `id` from each message payload.
- The message payload includes `id`, `name`, `mimeType`, `parents`, `document_type`, and `timestamp`.

### LAMBDA Env Vars

- ENABLED_FOLDERS
- GOOGLE_DRIVE_FOLDER_ID
- GOOGLE_SERVICE_ACCOUNT_PARAMETER_ID
- KILL_SWITCH
- SQS_PUBLISH_BATCH_SIZE
- SQS_QUEUE_URL

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
docker build -f Dockerfile.publisher -t hb-raw-data-pipeline:publisher .
```

If your image is already built, you can skip this step.

### 3) Tag the image for ECR

```bash
docker tag hb-raw-data-pipeline:publisher 317380566856.dkr.ecr.us-east-1.amazonaws.com/hb-raw-data-pipeline:publisher
```

### 4) Push image to ECR

```bash
docker push 317380566856.dkr.ecr.us-east-1.amazonaws.com/hb-raw-data-pipeline:publisher
```

## Consumer Deployment Notes

The consumer Lambda is scaffolded and ready for implementation. It is intended to:

- receive SQS messages from the publisher
- fetch the file content from Google Drive using the Drive file `id`
- run LLM + pre/post-processing
- move the processed file after successful handling

### Consumer Docker Image Build and Push

Build the consumer image using the consumer Dockerfile:

```bash
docker build -f Dockerfile.consumer -t hb-raw-data-pipeline:consumer .
```

Tag the consumer image for ECR:

```bash
docker tag hb-raw-data-pipeline:consumer 317380566856.dkr.ecr.us-east-1.amazonaws.com/hb-raw-data-pipeline:consumer
```

Push the consumer image to ECR:

```bash
docker push 317380566856.dkr.ecr.us-east-1.amazonaws.com/hb-raw-data-pipeline:consumer
```

### Consumer Lambda Setup

Tika Server Download: https://archive.apache.org/dist/tika/2.9.2/tika-server-standard-2.9.2.jar

- Create a second Lambda function for the consumer using the consumer container image.
- Set the Lambda handler to `consumer.lambda_handler`.
- **SQS Configuration**: 
  - Configure the event source mapping from the publisher SQS queue to the consumer Lambda.
  - Enable **Report batch item failures** in the SQS trigger settings to support partial batch failure reporting.
  - Set the visibility timeout to at least 6x the Lambda timeout (recommended for LLM processing).
- Add the Google service account credentials via `GOOGLE_SERVICE_ACCOUNT_PARAMETER_ID`.
- Set `SQS_QUEUE_URL` only if the consumer also needs to publish downstream messages later.
- Keep `LOG_LEVEL`, `APP_ENV`, and `PROJECT_NAME` consistent with the publisher setup.

## Production Schedule

- The production pipeline runs on a **weekly schedule**.

## Parameter Store Setup (Production)

For production, store the Google service account JSON in AWS Systems Manager Parameter Store instead of keeping the file in the container.

### 1) Create the parameter in the AWS Console

- Open the **AWS Console** and go to **Systems Manager** → **Parameter Store**.
- Choose **Create parameter**.
- Select **SecureString** as the parameter type.
- Paste the full Google service account JSON into the parameter value.
- Use the parameter name `hb-raw-data-pipeline_google-service-account`.
- Save the parameter in the same region as the Lambda function.

### 2) Configure Lambda environment variables in the AWS Console

- Open the **Lambda** function in the AWS Console.
- Go to **Configuration** → **Environment variables**.
- Add `GOOGLE_SERVICE_ACCOUNT_PARAMETER_ID=hb-raw-data-pipeline_google-service-account`.
- Keep `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_SHEETS_SPREADSHEET_ID`, and other non-secret values as regular environment variables.

### 3) Grant Lambda permission to read the parameter in IAM

- Open the Lambda execution role in **IAM**.
- Add permission for `ssm:GetParameter` on the parameter ARN.
- If the parameter uses a customer-managed KMS key, also allow the role to decrypt that key.
