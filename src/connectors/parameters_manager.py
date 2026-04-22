from __future__ import annotations
import json
import boto3
from typing import Any


def load_parameter_json(parameter_name: str) -> dict[str, Any]:
    client = boto3.client("ssm")
    response = client.get_parameter(Name=parameter_name, WithDecryption=True)
    parameter_value = response["Parameter"]["Value"]

    try:
        return json.loads(parameter_value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse Google service account JSON from parameter: {parameter_name}"
        ) from exc
