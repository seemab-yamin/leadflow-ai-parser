from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import boto3


def materialize_secret_to_tmp(secret_id: str) -> Path:
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)

    secret_string = response.get("SecretString")
    if not secret_string:
        raise ValueError(f"Secret {secret_id} does not contain a SecretString")

    json.loads(secret_string)

    file_name = f"google-service-account-{sha256(secret_id.encode('utf-8')).hexdigest()[:12]}.json"
    secret_path = Path("/tmp") / file_name
    secret_path.write_text(secret_string, encoding="utf-8")
    return secret_path