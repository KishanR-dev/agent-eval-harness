"""Unit tests for evaluation playground scenario mapping and runner execution."""

import pytest

from agent_eval_harness.playground.app import (
    SCENARIO_REGISTRY,
    create_playground_app,
    get_available_scenarios,
    get_scenario_id_by_name,
    run_scenario,
)


def test_scenario_registry_and_helpers() -> None:
    """Scenario registry provides valid display names and resolves correctly."""
    names = get_available_scenarios()
    assert len(names) == len(SCENARIO_REGISTRY)

    for case_id, info in SCENARIO_REGISTRY.items():
        resolved_id = get_scenario_id_by_name(info["name"])
        assert resolved_id == case_id


def test_get_scenario_id_invalid_name_raises() -> None:
    """Resolving an unknown scenario name raises ValueError."""
    with pytest.raises(ValueError, match="Unknown scenario display name"):
        get_scenario_id_by_name("NON-EXISTENT SCENARIO")


def test_run_scenario_qualified_e2e() -> None:
    """Running qualified scenario returns successful workflow output and passing evaluation."""
    display_name = SCENARIO_REGISTRY["CASE-001"]["name"]
    workflow_md, checks_md, judge_md, verdict_md, raw_json = run_scenario(display_name)

    assert "COMPLETED" in workflow_md
    assert "Synthetix Cloud Systems" in workflow_md
    assert "lifecycle_status" in checks_md
    assert "PASSED" in verdict_md
    assert "CASE-001" in raw_json


def test_run_scenario_disqualified_e2e() -> None:
    """Running disqualified scenario reflects skipped workflow and passing evaluation."""
    display_name = SCENARIO_REGISTRY["CASE-005"]["name"]
    workflow_md, checks_md, judge_md, verdict_md, raw_json = run_scenario(display_name)

    assert "SKIPPED_DISQUALIFIED" in workflow_md
    assert "Small Local Hardware Synth" in workflow_md
    assert "PASSED" in verdict_md
    assert "CASE-005" in raw_json


def test_run_scenario_error_e2e() -> None:
    """Running provider error scenario reflects failed workflow and controlled failure verdict."""
    display_name = SCENARIO_REGISTRY["CASE-ERR-01"]["name"]
    workflow_md, checks_md, judge_md, verdict_md, raw_json = run_scenario(display_name)

    assert "FAILED" in workflow_md
    assert "AdapterError" in workflow_md
    assert "CASE-ERR-01" in verdict_md
    assert "EXPECTED FAILURE" in verdict_md
    assert "Stage 1 Artifacts Preserved" in verdict_md


def test_run_scenario_judge_e2e() -> None:
    """Running workflow with judge scenario reflects judge verdict and pass status."""
    display_name = SCENARIO_REGISTRY["CASE-JUDGE-01"]["name"]
    workflow_md, checks_md, judge_md, verdict_md, raw_json = run_scenario(display_name)

    assert "COMPLETED" in workflow_md
    assert "relevance_positioning" in judge_md
    assert "4.0" in judge_md
    assert "PASSED" in verdict_md
    assert "Scenario ID:** `CASE-JUDGE-01`" in verdict_md
    assert "Underlying Evaluation Case ID:** `CASE-001`" in verdict_md
    assert '"scenario_id": "CASE-JUDGE-01"' in raw_json
    assert '"case_id": "CASE-001"' in raw_json


def test_run_scenario_invalid_name() -> None:
    """Running scenario with invalid display name returns error message."""
    workflow_md, checks_md, judge_md, verdict_md, raw_json = run_scenario("BAD NAME")
    assert "Error" in workflow_md
    assert checks_md == ""
    assert judge_md == ""
    assert verdict_md == ""
    assert raw_json == ""


def test_run_scenario_missing_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running scenario with missing fixture file returns error message."""
    monkeypatch.setitem(SCENARIO_REGISTRY["CASE-001"], "fixture", "non_existent.json")
    display_name = SCENARIO_REGISTRY["CASE-001"]["name"]
    workflow_md, checks_md, judge_md, verdict_md, raw_json = run_scenario(display_name)
    assert "Fixture file not found" in workflow_md


def test_create_playground_app_smoke() -> None:
    """Gradio Blocks app constructs successfully if gradio is installed, else skips cleanly."""
    try:
        import gradio  # noqa: F401
    except ImportError:
        pytest.skip("gradio optional dependency is not installed in current environment")

    demo = create_playground_app()
    assert demo is not None
