from __future__ import annotations

import json
from typing import Any

import boto3


def load_parameter_value(parameter_name: str) -> str:
    """Fetch a parameter value from AWS Systems Manager Parameter Store."""
    client = boto3.client("ssm")
    response = client.get_parameter(Name=parameter_name, WithDecryption=True)
    return response["Parameter"]["Value"]


def load_parameter_json(parameter_name: str) -> dict[str, Any]:
    """Fetch and parse a JSON parameter from AWS Systems Manager Parameter Store."""
    parameter_value = load_parameter_value(parameter_name)

    try:
        return json.loads(parameter_value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse JSON from parameter: {parameter_name}"
        ) from exc
