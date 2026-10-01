import datetime
import json
import uuid

import pytest

from gameclub_backend.modules.eventing_v2.application.deposit import V2DepositCreditCommand
from gameclub_backend.modules.eventing_v2.infrastructure.deposit_postgres import (
    PostgresV2DepositCreditRepository,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart


def create_command(**changes: object) -> V2DepositCreditCommand:
    values: dict[str, object] = {
        "payment_operation_id": uuid.UUID("00000000-0000-0000-0000-000000000301"),
        "client_id": uuid.UUID("00000000-0000-0000-0000-000000000302"),
        "session_id": uuid.UUID("00000000-0000-0000-0000-000000000303"),
        "device_id": "workstation-07",
        "amount_delta_cents": 500,
        "currency": "rub",
        "reason": "Пополнение баланса",
        "actor_id": "operator:12",
        "payment_parts": (PaymentPart("transfer", 500, "bank-ref-private"),),
        "cash_shift_id": None,
    }
    values.update(changes)
    return V2DepositCreditCommand(**values)  # type: ignore[arg-type]


def test_deposit_request_hash_is_stable_and_changes_with_semantic_request() -> None:
    command = create_command()

    assert command.currency == "RUB"
    assert command.request_hash == create_command().request_hash
    assert command.request_hash != create_command(reason="Другое основание").request_hash


def test_cash_deposit_requires_cash_shift() -> None:
    with pytest.raises(ValueError, match="cash shift"):
        create_command(payment_parts=(PaymentPart("cash", 500),))


def test_client_credit_event_contains_only_delta_and_no_payment_reference() -> None:
    command = create_command()
    occurred_at = datetime.datetime(2026, 9, 27, tzinfo=datetime.UTC)

    event = PostgresV2DepositCreditRepository._client_delivery_event(command, occurred_at)
    payload = json.loads(event.payload_json)

    assert event.operation_id == command.payment_operation_id
    assert payload == {
        "amount_delta_cents": 500,
        "currency": "RUB",
        "deposit_operation_id": str(command.payment_operation_id),
        "payment_method_types": ["transfer"],
    }
    assert "balance_cents" not in payload
    assert "bank-ref-private" not in event.payload_json


def test_deposit_creates_separate_client_and_confirmed_domain_events() -> None:
    command = create_command()
    occurred_at = datetime.datetime(2026, 9, 27, tzinfo=datetime.UTC)

    client_event = PostgresV2DepositCreditRepository._client_delivery_event(command, occurred_at)
    domain_event = PostgresV2DepositCreditRepository._confirmed_domain_event(command, occurred_at)

    assert client_event.event_id != domain_event.event_id
    assert client_event.operation_id == domain_event.operation_id
    assert json.loads(domain_event.payload_json) == {
        "amount_delta_cents": 500,
        "currency": "RUB",
        "deposit_operation_id": str(command.payment_operation_id),
        "payment_parts": [{"amount_cents": 500, "method": "transfer"}],
    }
    assert "bank-ref-private" not in domain_event.payload_json
