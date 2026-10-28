"""Unit tests for provider adapters and FakeLLMAdapter."""

import pytest

from agent_eval_harness.exceptions import AdapterError
from agent_eval_harness.providers import AdapterCall, FakeLLMAdapter


def test_fake_adapter_fifo_queue() -> None:
    """FakeLLMAdapter returns queued responses in FIFO order."""
    adapter = FakeLLMAdapter(responses=["first response", "second response"])
    assert adapter.complete("prompt 1") == "first response"
    assert adapter.complete("prompt 2") == "second response"


def test_fake_adapter_exhaustion_raises() -> None:
    """FakeLLMAdapter raises RuntimeError when responses are exhausted."""
    adapter = FakeLLMAdapter(responses=["single response"])
    assert adapter.complete("prompt 1") == "single response"

    with pytest.raises(RuntimeError) as exc_info:
        adapter.complete("prompt 2")
    assert "response queue exhausted" in str(exc_info.value)


def test_fake_adapter_adapter_error_injection() -> None:
    """FakeLLMAdapter raises configured AdapterError."""
    adapter = FakeLLMAdapter(exception_to_raise=AdapterError("Simulated provider timeout"))
    with pytest.raises(AdapterError) as exc_info:
        adapter.complete("prompt 1")
    assert "Simulated provider timeout" in str(exc_info.value)


def test_fake_adapter_unexpected_exception_injection() -> None:
    """FakeLLMAdapter raises unexpected exception directly."""
    adapter = FakeLLMAdapter(exception_to_raise=ValueError("Unexpected programming error"))
    with pytest.raises(ValueError) as exc_info:
        adapter.complete("prompt 1")
    assert "Unexpected programming error" in str(exc_info.value)


def test_fake_adapter_records_call_history() -> None:
    """FakeLLMAdapter records prompt and system_prompt history."""
    adapter = FakeLLMAdapter(responses=["resp 1", "resp 2"])
    adapter.complete("user prompt 1", system_prompt="sys prompt 1")
    adapter.complete("user prompt 2")

    assert len(adapter.calls) == 2
    assert adapter.calls[0] == AdapterCall(prompt="user prompt 1", system_prompt="sys prompt 1")
    assert adapter.calls[1] == AdapterCall(prompt="user prompt 2", system_prompt=None)
