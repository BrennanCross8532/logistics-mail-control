import pytest
from pydantic import ValidationError

from logistics_mail.shipment_service import (
    ProofOfDelivery,
    ShipmentEvent,
    ShipmentEventType,
    decide_outcome,
)


def test_verified_delivery_releases_notice_with_private_evidence_reference() -> None:
    event = ShipmentEvent(
        shipment_id="SHP-2048",
        event=ShipmentEventType.DELIVERED,
        proof=ProofOfDelivery(object_key="pod/SHP-2048.pdf", sha256="a" * 64),
    )

    outcome = decide_outcome(event)

    assert outcome.state == "delivered_verified"
    assert outcome.release_customer_notice is True
    assert outcome.evidence_reference == "pod/SHP-2048.pdf"


def test_delivery_without_proof_is_rejected_before_notification() -> None:
    with pytest.raises(ValidationError, match="require proof of delivery"):
        ShipmentEvent(shipment_id="SHP-2048", event=ShipmentEventType.DELIVERED)


def test_exception_is_held_for_manual_review() -> None:
    event = ShipmentEvent(
        shipment_id="SHP-4096",
        event=ShipmentEventType.EXCEPTION,
        exception_reason="recipient identity mismatch",
    )

    outcome = decide_outcome(event)

    assert outcome.state == "manual_review"
    assert outcome.release_customer_notice is False

