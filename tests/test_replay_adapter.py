"""Unit tests for ReplayingLLMAdapter sequential playback, error paths, and stage checks."""

from pathlib import Path

import pytest

from agent_eval_harness.exceptions import (
    AdapterError,
    FixtureCorruptedError,
    FixtureExhaustedError,
    FixtureNotFoundError,
)
from agent_eval_harness.fixtures import ExchangeStage, RecordedExchange, ReplayFixture
from agent_eval_harness.providers import ReplayingLLMAdapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures"


# ============================================================================
# 1. Loading & Factory Tests
# ============================================================================


def test_replaying_adapter_loads_canonical_fixture() -> None:
    """ReplayingLLMAdapter loads canonical fixture file successfully."""
    path = FIXTURES_DIR / "qualified_workflow.json"
    adapter = ReplayingLLMAdapter.from_fixture_file(path)
    assert adapter.fixture.fixture_id == "FIX-QUALIFIED-001"
    assert adapter.cursor == 0
    assert adapter.remaining_calls == 2
    assert len(adapter.calls) == 0


def test_replaying_adapter_missing_file_raises_fixture_not_found(tmp_path: Path) -> None:
    """ReplayingLLMAdapter raises FixtureNotFoundError when file path does not exist."""
    missing_path = tmp_path / "non_existent_fixture.json"
    with pytest.raises(FixtureNotFoundError, match="Fixture file not found"):
        ReplayingLLMAdapter.from_fixture_file(missing_path)


def test_replaying_adapter_malformed_json_raises_corrupted(tmp_path: Path) -> None:
    """ReplayingLLMAdapter raises FixtureCorruptedError on invalid JSON syntax."""
    bad_json = tmp_path / "bad_syntax.json"
    bad_json.write_text("{ this is not valid json }", encoding="utf-8")
    with pytest.raises(FixtureCorruptedError, match="Failed to read or parse fixture JSON"):
        ReplayingLLMAdapter.from_fixture_file(bad_json)


def test_replaying_adapter_invalid_schema_raises_corrupted(tmp_path: Path) -> None:
    """ReplayingLLMAdapter raises FixtureCorruptedError on schema validation failure."""
    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text(
        '{"schema_version": "1.0.0", "fixture_id": "F1", "description": "D1", '
        '"is_synthetic": true, "exchanges": []}',
        encoding="utf-8",
    )
    with pytest.raises(FixtureCorruptedError, match="Fixture validation failed"):
        ReplayingLLMAdapter.from_fixture_file(bad_schema)


# ============================================================================
# 2. Sequential Playback, State, & Exhaustion Tests
# ============================================================================


def test_replaying_adapter_sequential_playback_and_reset() -> None:
    """ReplayingLLMAdapter yields responses sequentially and resets cleanly."""
    fixture = ReplayFixture(
        fixture_id="SEQ-001",
        description="Sequential test",
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.LEAD_QUALIFICATION,
                response_text="Resp 0",
            ),
            RecordedExchange(
                call_index=1,
                stage=ExchangeStage.OUTREACH_DRAFTING,
                response_text="Resp 1",
            ),
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=False)
    assert adapter.cursor == 0
    assert adapter.remaining_calls == 2

    # Call 0
    resp0 = adapter.complete(prompt="Prompt 0", system_prompt="Sys 0")
    assert resp0 == "Resp 0"
    assert adapter.cursor == 1
    assert adapter.remaining_calls == 1
    assert len(adapter.calls) == 1
    assert adapter.calls[0].prompt == "Prompt 0"
    assert adapter.calls[0].system_prompt == "Sys 0"

    # Call 1
    resp1 = adapter.complete(prompt="Prompt 1")
    assert resp1 == "Resp 1"
    assert adapter.cursor == 2
    assert adapter.remaining_calls == 0
    assert len(adapter.calls) == 2

    # Reset
    adapter.reset()
    assert adapter.cursor == 0
    assert adapter.remaining_calls == 2
    assert len(adapter.calls) == 0


def test_replaying_adapter_exhaustion_raises_fixture_exhausted() -> None:
    """ReplayingLLMAdapter raises FixtureExhaustedError when calls exceed exchanges."""
    fixture = ReplayFixture(
        fixture_id="EXH-001",
        description="Exhaustion test",
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.LEAD_QUALIFICATION,
                response_text="Single response",
            )
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=False)
    adapter.complete(prompt="Call 1")

    with pytest.raises(FixtureExhaustedError, match="exhausted: call index 1 exceeded 1"):
        adapter.complete(prompt="Call 2")

    # Confirm FixtureExhaustedError subclasses AdapterError
    assert issubclass(FixtureExhaustedError, AdapterError)


# ============================================================================
# 3. Stage Consistency & Error Injection Tests
# ============================================================================


def test_replaying_adapter_stage_verification_success() -> None:
    """ReplayingLLMAdapter detects matching stages from prompt and system prompt."""
    fixture = ReplayFixture(
        fixture_id="STAGE-001",
        description="Stage check test",
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
            RecordedExchange(
                call_index=2,
                stage=ExchangeStage.JUDGE,
                response_text="Judge response",
            ),
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=True)

    # Lead qualification call
    lead_res = adapter.complete(
        prompt="Evaluate the following inbound lead:\n...",
        system_prompt="You are an AI Lead Qualification Agent.",
    )
    assert lead_res == "Lead response"

    # Outreach drafting call
    draft_res = adapter.complete(
        prompt="Draft an outreach message based on this handoff:\n...",
        system_prompt="You are an AI Outreach Drafting Agent.",
    )
    assert draft_res == "Draft response"

    # Judge call
    judge_res = adapter.complete(
        prompt="=== EVALUATION TARGET DATA ===\n<untrusted_evaluated_content>",
        system_prompt="You are an expert evaluator for enterprise B2B...",
    )
    assert judge_res == "Judge response"


def test_replaying_adapter_stage_mismatch_raises_adapter_error() -> None:
    """ReplayingLLMAdapter raises AdapterError when detected stage violates fixture stage."""
    fixture = ReplayFixture(
        fixture_id="MISMATCH-001",
        description="Mismatch test",
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.OUTREACH_DRAFTING,  # Fixture expects stage 2
                response_text="Draft response",
            )
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=True)

    # Agent unexpectedly sends a Lead Qualification prompt
    with pytest.raises(AdapterError, match="Replay stage mismatch at call 0"):
        adapter.complete(
            prompt="Evaluate the following inbound lead:\n...",
            system_prompt="You are an AI Lead Qualification Agent.",
        )


def test_replaying_adapter_verify_stage_disabled_bypasses_check() -> None:
    """verify_stage=False permits stage mismatch without raising error."""
    fixture = ReplayFixture(
        fixture_id="BYPASS-001",
        description="Bypass test",
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.OUTREACH_DRAFTING,
                response_text="Draft response",
            )
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=False)
    resp = adapter.complete(
        prompt="Evaluate the following inbound lead:\n...",
        system_prompt="You are an AI Lead Qualification Agent.",
    )
    assert resp == "Draft response"


def test_replaying_adapter_simulated_provider_error() -> None:
    """ReplayingLLMAdapter raises AdapterError with recorded error_to_raise string."""
    fixture = ReplayFixture(
        fixture_id="ERR-001",
        description="Error injection test",
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.LEAD_QUALIFICATION,
                error_to_raise="Simulated 503 Service Unavailable",
            )
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=False)

    with pytest.raises(AdapterError, match="Simulated 503 Service Unavailable"):
        adapter.complete(prompt="Some prompt")


def test_replaying_adapter_undetected_stage_fails_when_verify_stage_enabled() -> None:
    """When verify_stage=True, unrecognized prompt cannot silently bypass stage consistency."""
    fixture = ReplayFixture(
        fixture_id="UNDETECTED-001",
        description="Undetected stage test",
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.LEAD_QUALIFICATION,
                response_text="Custom output",
            )
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=True)
    with pytest.raises(
        AdapterError,
        match=(
            "Replay stage mismatch at call 0: fixture expected "
            "'lead_qualification', but detected 'unknown'"
        ),
    ):
        adapter.complete(prompt="Generic unadorned prompt", system_prompt=None)


def test_replaying_adapter_undetected_stage_permitted_when_verify_stage_disabled() -> None:
    """When verify_stage=False, unrecognized prompt proceeds without stage validation."""
    fixture = ReplayFixture(
        fixture_id="UNDETECTED-002",
        description="Undetected stage test with check disabled",
        exchanges=[
            RecordedExchange(
                call_index=0,
                stage=ExchangeStage.LEAD_QUALIFICATION,
                response_text="Custom output",
            )
        ],
    )
    adapter = ReplayingLLMAdapter(fixture=fixture, verify_stage=False)
    resp = adapter.complete(prompt="Generic unadorned prompt", system_prompt=None)
    assert resp == "Custom output"
