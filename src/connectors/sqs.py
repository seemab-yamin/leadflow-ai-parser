from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import uuid4

import boto3

LOGGER = logging.getLogger(__name__)


class SQSPublisher:
    """SQS Publisher connector for publishing messages to AWS SQS queue."""

    def __init__(self, queue_url: str):
        """Initialize SQS publisher.

        Args:
            queue_url: AWS SQS queue URL
        """
        self.queue_url = queue_url
        self.client = boto3.client("sqs")

    def publish_message(
        self,
        message: dict[str, Any],
        max_retries: int = 3,
        initial_backoff: float = 1.0,
    ) -> bool:
        """Publish message to SQS queue with retry logic.

        Args:
            message: Message payload to publish
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff in seconds for exponential backoff

        Returns:
            True if successful, False otherwise

        Error Handling:
        - Retry with exponential backoff on failure
        - Log all failures for monitoring
        """
        body = json.dumps(message, default=str)

        for attempt in range(max_retries + 1):
            try:
                response = self.client.send_message(
                    QueueUrl=self.queue_url,
                    MessageBody=body,
                )
                LOGGER.info(
                    "Published message to SQS queue=%s message_id=%s",
                    self.queue_url,
                    response.get("MessageId"),
                )
                return True
            except Exception as exc:
                if attempt < max_retries:
                    backoff = initial_backoff * (2**attempt)
                    LOGGER.warning(
                        "SQS publish failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        max_retries + 1,
                        backoff,
                        exc,
                    )
                    time.sleep(backoff)
                    continue

                LOGGER.error(
                    "Failed to publish message after %d attempts: %s",
                    max_retries + 1,
                    exc,
                )
                return False

        return False

    def publish_batch(
        self,
        messages: list[dict[str, Any]],
        batch_size: int = 10,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Publish multiple messages in batch to SQS.

        Args:
            messages: List of message payloads
            batch_size: Number of messages per SQS batch request (1-10)
            max_retries: Maximum number of retry attempts for failed batch entries
            initial_backoff: Initial backoff in seconds for exponential backoff

        Returns:
            Tuple of (successful_count, failed_messages)
        """
        if not messages:
            return (0, [])

        if not 1 <= batch_size <= 10:
            raise ValueError("batch_size must be between 1 and 10")

        successful_count = 0
        failed_messages: list[dict[str, Any]] = []

        for start_idx in range(0, len(messages), batch_size):
            chunk = messages[start_idx : start_idx + batch_size]
            pending_items = [
                {
                    "Id": f"msg-{idx}-{uuid4().hex[:8]}",
                    "message": message,
                }
                for idx, message in enumerate(chunk)
            ]

            attempt = 0
            while pending_items and attempt <= max_retries:
                try:
                    batch_entries = [
                        {
                            "Id": item["Id"],
                            "MessageBody": json.dumps(item["message"], default=str),
                        }
                        for item in pending_items
                    ]
                    response = self.client.send_message_batch(
                        QueueUrl=self.queue_url,
                        Entries=batch_entries,
                    )

                    successful = response.get("Successful", [])
                    failed = response.get("Failed", [])
                    successful_count += len(successful)

                    if not failed:
                        break

                    retryable_ids: set[str] = set()
                    for failed_entry in failed:
                        entry_id = failed_entry.get("Id")
                        code = failed_entry.get("Code")
                        message = failed_entry.get("Message")
                        sender_fault = bool(failed_entry.get("SenderFault"))
                        matching_item = next(
                            (
                                item
                                for item in pending_items
                                if item["Id"] == entry_id
                            ),
                            None,
                        )

                        if sender_fault or matching_item is None:
                            if matching_item is not None:
                                failed_messages.append(matching_item["message"])
                            LOGGER.error(
                                "SQS sender fault for entry_id=%s code=%s message=%s",
                                entry_id,
                                code,
                                message,
                            )
                        else:
                            retryable_ids.add(entry_id)

                    pending_items = [
                        item for item in pending_items if item["Id"] in retryable_ids
                    ]

                    if pending_items and attempt < max_retries:
                        backoff = initial_backoff * (2**attempt)
                        LOGGER.warning(
                            "Retrying %d failed SQS batch entries in %.1fs",
                            len(pending_items),
                            backoff,
                        )
                        time.sleep(backoff)
                    elif pending_items:
                        failed_messages.extend(
                            item["message"] for item in pending_items
                        )
                        LOGGER.error(
                            "Failed to publish %d batch messages after %d attempts",
                            len(pending_items),
                            max_retries + 1,
                        )
                        break
                except Exception as exc:
                    if attempt < max_retries:
                        backoff = initial_backoff * (2**attempt)
                        LOGGER.warning(
                            "SQS batch publish failed (attempt %d/%d), retrying in %.1fs: %s",
                            attempt + 1,
                            max_retries + 1,
                            backoff,
                            exc,
                        )
                        time.sleep(backoff)
                    else:
                        failed_messages.extend(
                            item["message"] for item in pending_items
                        )
                        LOGGER.error(
                            "SQS batch publish failed after %d attempts: %s",
                            max_retries + 1,
                            exc,
                        )
                        break

                attempt += 1

        return successful_count, failed_messages
