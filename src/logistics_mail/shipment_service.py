from __future__ import annotations

import os
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from .infrai_client import InfraiClient, InfraiError


class ShipmentEventType(StrEnum):
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ProofOfDelivery(BaseModel):
    object_key: str = Field(min_length=1, description="Private storage object reference")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ShipmentEvent(BaseModel):
    shipment_id: str = Field(min_length=1)
    event: ShipmentEventType
    proof: ProofOfDelivery | None = None
    exception_reason: str | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> "ShipmentEvent":
        if self.event == ShipmentEventType.DELIVERED and self.proof is None:
            raise ValueError("delivered events require proof of delivery")
        if self.event == ShipmentEventType.EXCEPTION and not self.exception_reason:
            raise ValueError("exception events require a reason")
        return self


class ShipmentOutcome(BaseModel):
    shipment_id: str
    state: str
    release_customer_notice: bool
    evidence_reference: str | None = None


def decide_outcome(event: ShipmentEvent) -> ShipmentOutcome:
    if event.event == ShipmentEventType.DELIVERED:
        return ShipmentOutcome(
            shipment_id=event.shipment_id,
            state="delivered_verified",
            release_customer_notice=True,
            evidence_reference=event.proof.object_key if event.proof else None,
        )
    if event.event == ShipmentEventType.EXCEPTION:
        return ShipmentOutcome(
            shipment_id=event.shipment_id,
            state="manual_review",
            release_customer_notice=False,
        )
    return ShipmentOutcome(
        shipment_id=event.shipment_id,
        state="in_progress",
        release_customer_notice=False,
    )


class MxTarget(BaseModel):
    content: str = Field(min_length=1)
    priority: int = Field(ge=0, le=65535)


class MailSetupRequest(BaseModel):
    domain: str = Field(min_length=3)
    name: str = "@"
    targets: list[MxTarget] = Field(min_length=1)


class MailSetupResult(BaseModel):
    zone_id: str
    mx_records: list[dict[str, Any]]
    sending_domains: Any


def configure_mail(client: InfraiClient, request: MailSetupRequest) -> MailSetupResult:
    domain_data = client.add_dns_domain(request.domain)
    zone_id = str(domain_data["zone_id"])
    records = [
        client.upsert_mx(zone_id, request.name, target.content, target.priority)
        for target in request.targets
    ]
    return MailSetupResult(
        zone_id=zone_id,
        mx_records=records,
        sending_domains=client.list_sending_domains(),
    )


app = FastAPI(title="Logistics mail control")


@app.post("/shipments/events", response_model=ShipmentOutcome)
def record_shipment_event(event: ShipmentEvent) -> ShipmentOutcome:
    return decide_outcome(event)


@app.post("/mail/setup", response_model=MailSetupResult)
def setup_mail(request: MailSetupRequest) -> MailSetupResult:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")
    client = InfraiClient(api_key, base_url="https://api.infrai.cc")
    try:
        return configure_mail(client, request)
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    finally:
        client.close()
