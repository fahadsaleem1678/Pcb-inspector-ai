"""Standard SQS transport. Payloads contain identities, never trusted paths or owners."""

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pcb_inspector.aws import aws_client
from pcb_inspector.config import Settings


@dataclass(frozen=True)
class Delivery:
    receipt: str
    body: str

    def identities(self) -> tuple[str, str]:
        if len(self.body) > 1024:
            raise ValueError("Oversized queue event")
        payload = json.loads(self.body)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"version", "event_id", "inspection_id"}
            or type(payload["version"]) is not int
            or payload["version"] != 1
        ):
            raise ValueError("Invalid queue event")
        for field in ("event_id", "inspection_id"):
            if not isinstance(payload[field], str) or str(UUID(payload[field])) != payload[field]:
                raise ValueError("Invalid event identity")
        return payload["event_id"], payload["inspection_id"]


class SQSQueue:
    def __init__(self, client: Any, settings: Settings):
        self.client = client
        self.settings = settings
        self.url = settings.sqs_queue_url

    @classmethod
    def from_settings(cls, settings: Settings) -> "SQSQueue":
        return cls(aws_client("sqs", settings), settings)

    def validate(self) -> None:
        attributes = self.client.get_queue_attributes(
            QueueUrl=self.url,
            AttributeNames=["QueueArn", "RedrivePolicy", "FifoQueue"],
        )["Attributes"]
        policy = json.loads(attributes.get("RedrivePolicy", "{}"))
        source = attributes["QueueArn"].split(":")
        target = str(policy.get("deadLetterTargetArn", "")).split(":")
        if (
            attributes.get("FifoQueue", "false") != "false"
            or len(source) != 6
            or len(target) != 6
            or source[:5] != target[:5]
            or source == target
            or target[2] != "sqs"
            or not target[5]
            or target[5].endswith(".fifo")
            or int(policy.get("maxReceiveCount", 0)) < self.settings.max_attempts + 2
        ):
            raise ValueError(
                "Standard SQS queue requires a same-account/region DLQ and retry margin"
            )

    def send(self, event_id: str, inspection_id: str) -> None:
        body = json.dumps({"version": 1, "event_id": event_id, "inspection_id": inspection_id})
        Delivery("", body).identities()
        self.client.send_message(QueueUrl=self.url, MessageBody=body)

    def receive(self) -> Delivery | None:
        messages = self.client.receive_message(
            QueueUrl=self.url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=self.settings.sqs_visibility_seconds,
        ).get("Messages", [])
        if not messages:
            return None
        return Delivery(messages[0]["ReceiptHandle"], messages[0]["Body"])

    def renew(self, delivery: Delivery, seconds: int | None = None) -> None:
        self.client.change_message_visibility(
            QueueUrl=self.url,
            ReceiptHandle=delivery.receipt,
            VisibilityTimeout=self.settings.sqs_visibility_seconds if seconds is None else seconds,
        )

    def delete(self, delivery: Delivery) -> None:
        self.client.delete_message(QueueUrl=self.url, ReceiptHandle=delivery.receipt)
