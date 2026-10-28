"""Unit tests for fixture schemas, validation invariants, and canonical fixture files."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_eval_harness.fixtures import ExchangeStage, RecordedExchange, ReplayFixture

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures"


# ============================================================================
# 1. Model & Validation Invariant Tests
# ============================================================================


def test_recorded_exchange_valid_response() -> None:
    """RecordedExchange accepts valid response_text with valid stage."""
    exchange = RecordedExchange(
        call_index=0,
        stage=ExchangeStage.LEAD_QUALIFICATION,
        response_text='{"status": "ok"}',
    )
    assert exchange.call_index == 0
    assert exchange.stage == ExchangeStage.LEAD_QUALIFICATION
    assert exchange.response_text == '{"status": "ok"}'
    assert exchange.error_to_raise is None


def test_recorded_exchange_valid_simulated_error() -> None:
    """RecordedExchange accepts valid error_to_raise with no response_text."""
    exchange = RecordedExchange(
        call_index=1,
        stage=ExchangeStage.OUTREACH_DRAFTING,
        error_to_raise="Simulated 500 Internal Server Error",
    )
    assert exchange.call_index == 1
    assert exchange.response_text is None
    assert exchange.error_to_raise == "Simulated 500 Internal Server Error"


def test_recorded_exchange_rejects_neither_payload() -> None:
    """RecordedExchange rejects payload when neither response nor error is supplied."""
    with pytest.raises(ValidationError, match="requires exactly one"):
        RecordedExchange(
            call_index=0,
            stage=ExchangeStage.LEAD_QUALIFICATION,
        )


def test_recorded_exchange_rejects_both_payloads() -> None:
    """RecordedExchange rejects payload when both response and error are supplied."""
    with pytest.raises(ValidationError, match="requires exactly one"):
        RecordedExchange(
            call_index=0,
            stage=ExchangeStage.LEAD_QUALIFICATION,
            response_text="some text",
            error_to_raise="some error",
        )


def test_recorded_exchange_rejects_whitespace_payload() -> None:
    """RecordedExchange rejects empty or whitespace-only response_text."""
    with pytest.raises(ValidationError, match="requires exactly one"):
        RecordedExchange(
            call_index=0,
            stage=ExchangeStage.LEAD_QUALIFICATION,
            response_text="   \n  ",
        )


def test_recorded_exchange_credential_scan_safeguard() -> None:
    """RecordedExchange rejects response_text containing likely credential patterns."""
    fake_key = "sk-" + "a" * 25
    with pytest.raises(ValidationError, match="likely credential pattern"):
        RecordedExchange(
            call_index=0,
            stage=ExchangeStage.LEAD_QUALIFICATION,
            response_text=f'{{"key": "{fake_key}"}}',
        )

    fake_bearer = "Bearer " + "b" * 25
    with pytest.raises(ValidationError, match="likely credential pattern"):
        RecordedExchange(
            call_index=0,
            stage=ExchangeStage.LEAD_QUALIFICATION,
            response_text=f'{{"token": "{fake_bearer}"}}',
        )


def test_recorded_exchange_credential_scan_error_to_raise() -> None:
    """RecordedExchange rejects error_to_raise containing likely credential patterns."""
    fake_key = "sk-" + "c" * 25
    with pytest.raises(ValidationError, match="likely credential pattern"):
        RecordedExchange(
            call_index=0,
            stage=ExchangeStage.LEAD_QUALIFICATION,
            error_to_raise=f"Upstream provider error with key {fake_key}",
        )


def test_recorded_exchange_invalid_stage() -> None:
    """RecordedExchange rejects stage strings outside ExchangeStage enum."""
    with pytest.raises(ValidationError):
        RecordedExchange(
            call_index=0,
            stage="invalid_stage_name",  # type: ignore[arg-type]
            response_text="{}",
        )


def test_replay_fixture_valid() -> None:
    """ReplayFixture accepts valid sequential exchanges."""
    fixture = ReplayFixture(
        fixture_id="TEST-FIX-001",
        description="Test fixture description.",
        is_synthetic=True,
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.LEAD_QUALIFICATION,
                response_text="Lead response",
            ),
            RecordedExchange(
                call_index=1,
                stage=ExchangeStage.OUTREACH_DRAFTING,
                response_text="Draft response",
            ),
        ],
    )
    assert fixture.schema_version == "1.0.0"
    assert fixture.fixture_id == "TEST-FIX-001"
    assert len(fixture.exchanges) == 2


def test_replay_fixture_rejects_non_synthetic() -> None:
    """ReplayFixture rejects is_synthetic=False."""
    with pytest.raises(ValidationError, match="must have is_synthetic=True"):
        ReplayFixture(
            fixture_id="TEST-FIX-002",
            description="Non-synthetic fixture",
            is_synthetic=False,
            exchanges=[
                RecordedExchange(
                    call_index=0,
                    stage=ExchangeStage.LEAD_QUALIFICATION,
                    response_text="{}",
                )
            ],
        )


def test_replay_fixture_rejects_non_sequential_indices() -> None:
    """ReplayFixture rejects exchanges with out-of-order or gap indices."""
    with pytest.raises(ValidationError, match="call_index sequence must start at 0"):
        ReplayFixture(
            fixture_id="TEST-FIX-003",
            description="Non-sequential fixture",
            exchanges=[
                RecordedExchange(
                    call_index=1,
                    stage=ExchangeStage.LEAD_QUALIFICATION,
                    response_text="{}",
                )
            ],
        )

    with pytest.raises(ValidationError, match="call_index sequence must start at 0"):
        ReplayFixture(
            fixture_id="TEST-FIX-004",
            description="Gap fixture",
            exchanges=[
                RecordedExchange(
                    call_index=0,
                    stage=ExchangeStage.LEAD_QUALIFICATION,
                    response_text="{}",
                ),
                RecordedExchange(
                    call_index=2,  # Should be 1
                    stage=ExchangeStage.OUTREACH_DRAFTING,
                    response_text="{}",
                ),
            ],
        )


def test_replay_fixture_rejects_unsupported_version() -> None:
    """ReplayFixture rejects schema_version other than '1.0.0'."""
    with pytest.raises(ValidationError):
        ReplayFixture(
            schema_version="2.0.0",  # type: ignore[arg-type]
            fixture_id="TEST-FIX-005",
            description="Unsupported version",
            exchanges=[
                RecordedExchange(
                    call_index=0,
                    stage=ExchangeStage.LEAD_QUALIFICATION,
                    response_text="{}",
                )
            ],
        )


# ============================================================================
# 2. Canonical Fixture Files Inspection Tests
# ============================================================================


@pytest.mark.parametrize(
    "filename",
    [
        "qualified_workflow.json",
        "disqualified_workflow.json",
        "provider_error_workflow.json",
        "workflow_with_judge.json",
    ],
)
def test_canonical_fixtures_exist_and_validate(filename: str) -> None:
    """Each canonical synthetic fixture file exists, parses, and validates strictly."""
    import json

    file_path = FIXTURES_DIR / filename
    assert file_path.is_file(), f"Expected fixture file to exist: {file_path}"

    raw_text = file_path.read_text(encoding="utf-8")
    assert "sk-" not in raw_text
    assert "Bearer " not in raw_text
    assert "ghp_" not in raw_text

    data = json.loads(raw_text)
    fixture = ReplayFixture.model_validate(data)
    assert fixture.is_synthetic is True
    assert fixture.schema_version == "1.0.0"
    assert len(fixture.exchanges) >= 1
