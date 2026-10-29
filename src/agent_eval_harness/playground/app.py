"""Interactive Evaluation Playground runner using Gradio and core harness logic."""

from pathlib import Path
from typing import Any

from agent_eval_harness.agents import LeadQualificationAgent, OutreachDrafterAgent
from agent_eval_harness.coordinator import WorkflowCoordinator
from agent_eval_harness.evaluation import DeterministicEvaluationRunner, LLMJudge
from agent_eval_harness.evaluation.dataset import load_dataset
from agent_eval_harness.providers import ReplayingLLMAdapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATASET_PATH = PROJECT_ROOT / "datasets" / "synthetic_cases.json"
FIXTURES_DIR = PROJECT_ROOT / "fixtures"

# Mapping of stable scenario IDs to fixture filenames and descriptions
SCENARIO_REGISTRY: dict[str, dict[str, str]] = {
    "CASE-001": {
        "name": "CASE-001: Enterprise Cloud Compliance (Qualified)",
        "fixture": "qualified_workflow.json",
        "description": (
            "Standard qualified enterprise cloud infrastructure prospect "
            "seeking SOC2 compliance automation."
        ),
    },
    "CASE-005": {
        "name": "CASE-005: Local Retail Hardware (Disqualified)",
        "fixture": "disqualified_workflow.json",
        "description": (
            "Single-stage disqualified prospect workflow where Stage 2 "
            "outreach is skipped by coordinator."
        ),
    },
    "CASE-ERR-01": {
        "name": "CASE-ERR-01: Simulated Provider Outage (Error / Failure)",
        "fixture": "provider_error_workflow.json",
        "description": (
            "Simulated upstream provider failure raising AdapterError during "
            "Stage 2 while preserving Stage 1 artifacts."
        ),
    },
    "CASE-JUDGE-01": {
        "name": "CASE-JUDGE-01: Full Workflow with Rubric Judge (Pass)",
        "fixture": "workflow_with_judge.json",
        "description": (
            "Complete three-tier evaluation workflow including Lead Qualification, "
            "Outreach Drafting, and LLM Judge evaluation."
        ),
    },
}


def get_available_scenarios() -> list[str]:
    """Return list of scenario display names for UI selection."""
    return [info["name"] for info in SCENARIO_REGISTRY.values()]


def get_scenario_id_by_name(display_name: str) -> str:
    """Resolve display name back to stable scenario ID."""
    for case_id, info in SCENARIO_REGISTRY.items():
        if info["name"] == display_name:
            return case_id
    raise ValueError(f"Unknown scenario display name: {display_name}")


def run_scenario(display_name: str) -> tuple[str, str, str, str, str]:
    """Execute selected scenario through core harness and format UI output sections.

    Returns:
        Tuple of (workflow_status_md, checks_md, judge_md, verdict_md, raw_json_summary)
    """
    try:
        case_id = get_scenario_id_by_name(display_name)
    except Exception as exc:
        return f"### Error\nInvalid scenario: {exc}", "", "", "", ""

    scenario_info = SCENARIO_REGISTRY[case_id]
    fixture_path = FIXTURES_DIR / scenario_info["fixture"]
    if not fixture_path.is_file():
        return f"### Error\nFixture file not found: {scenario_info['fixture']}", "", "", "", ""

    # Load dataset case
    try:
        cases = load_dataset(DATASET_PATH)
        target_case_id = "CASE-001" if case_id in ("CASE-ERR-01", "CASE-JUDGE-01") else case_id
        case = next(c for c in cases if c.case_id == target_case_id)
    except Exception as exc:
        return f"### Error\nFailed to load dataset: {exc}", "", "", "", ""

    # Initialize replaying adapter and coordinator
    try:
        adapter = ReplayingLLMAdapter.from_fixture_file(fixture_path, verify_stage=True)
        lead_agent = LeadQualificationAgent(adapter=adapter)
        outreach_agent = OutreachDrafterAgent(adapter=adapter)
        coordinator = WorkflowCoordinator(lead_agent=lead_agent, outreach_agent=outreach_agent)

        judge = None
        if case_id == "CASE-JUDGE-01":
            judge = LLMJudge(adapter=adapter)

        # Run workflow
        result = coordinator.run(lead_input=case.lead_input, outreach_config=case.outreach_config)

        # Run evaluation
        runner = DeterministicEvaluationRunner(judge=judge)
        eval_result = runner.evaluate_result(case=case, result=result, judge=judge)
    except Exception as exc:
        return f"### Execution Error\n{type(exc).__name__}: {exc}", "", "", "", ""

    # 1. Format Workflow Status & Outputs
    workflow_md = f"""### Workflow Execution Summary
- **Scenario ID:** `{case_id}`
- **Description:** `{scenario_info["description"]}`
- **Coordinator Status:** `{result.status.value}`
- **Failed Stage:** `{result.failed_stage or "None"}`
- **Error Category:** `{result.error_category or "None"}`
"""
    if result.lead_result:
        workflow_md += f"""
#### Stage 1: Lead Qualification Result
- **Company Name:** `{result.lead_result.company_name}`
- **Industry:** `{result.lead_result.industry}`
- **Qualification Status:** `{result.lead_result.qualification_status.value}`
- **Fit Score:** `{result.lead_result.fit_score}` / 100
- **Summary:** {result.lead_result.summary}
- **Key Pain Points:** {", ".join(result.lead_result.key_pain_points)}
"""
    if result.draft_result:
        workflow_md += f"""
#### Stage 2: Outreach Draft Result
- **Channel:** `{result.draft_result.channel.value}`
- **Subject Line:** `{result.draft_result.subject_line or "N/A"}`
- **Body:** {result.draft_result.body}
- **Call to Action:** `{result.draft_result.call_to_action}`
- **Word Count:** `{result.draft_result.word_count}` words
"""
    elif result.status.value.startswith("SKIPPED"):
        workflow_md += (
            "\n*Stage 2 Outreach Drafting was skipped by the coordinator "
            "due to lead qualification status.*\n"
        )

    # 2. Format Deterministic Checks (Tier 1)
    checks_md = "### Tier 1: Deterministic Policy Checks\n\n"
    if not eval_result.checks:
        checks_md += "*No deterministic checks executed.*\n"
    else:
        checks_md += "| Check Name | Severity | Status | Message |\n| :--- | :--- | :--- | :--- |\n"
        for cr in eval_result.checks:
            status_icon = "✅ PASS" if cr.passed else "❌ FAIL"
            checks_md += (
                f"| `{cr.check_name}` | `{cr.severity.value}` | "
                f"**{status_icon}** | {cr.message} |\n"
            )

    # 3. Format LLM Judge Verdict (Tier 2)
    judge_md = "### Tier 2: Rubric-Based LLM Judge\n\n"
    if (
        eval_result.judge_verdict is None
        or eval_result.judge_verdict.status.value == "SKIPPED_NON_APPLICABLE"
    ):
        judge_md += (
            "*LLM Judge was not executed or was skipped "
            "(non-applicable for this workflow execution path).*\n"
        )
    else:
        jv = eval_result.judge_verdict
        judge_md += f"- **Judge Status:** `{jv.status.value}`\n"
        judge_md += f"- **Model Identifier:** `{jv.model_identifier}`\n"
        judge_md += f"- **Derived Overall Score:** `{jv.overall_score}` / 4.0\n"
        judge_md += (
            f"- **Judge Passed (Dimension Veto all $\\ge 3$):** "
            f"`{'YES ✅' if jv.passed else 'NO ❌'}`\n\n"
        )
        if jv.scores:
            judge_md += "| Dimension | Score | Rationale |\n| :--- | :---: | :--- |\n"
            for score in jv.scores:
                score_badge = f"{score.score} / 4"
                if score.score < 3:
                    score_badge += " ⚠️ (Veto Fail)"
                judge_md += (
                    f"| `{score.dimension.value}` | **{score_badge}** | {score.rationale} |\n"
                )

    # 4. Format Final Verdict & Summary
    if case_id == "CASE-ERR-01":
        verdict_icon = "⚠️ EXPECTED FAILURE (FAULT TOLERANCE DEMO)"
        verdict_md = f"""### Final Evaluation Verdict: {verdict_icon}
- **Scenario ID:** `{case_id}`
- **Execution Status:** `{result.status.value}` (Simulated Provider Outage Handled Gracefully)
- **Error Category:** `{result.error_category}`
- **Stage 1 Artifacts Preserved:** `YES ✅` (Retained despite Stage 2 failure)
- **Explanation:** Demonstrates graceful fault isolation. The upstream provider failure
  during outreach drafting is caught and structured as a controlled `FAILED` status
  while preserving intermediate qualification artifacts.
"""
    else:
        verdict_icon = "🟢 PASSED" if eval_result.passed else "🔴 FAILED"
        verdict_md = f"""### Final Evaluation Verdict: {verdict_icon}
- **Scenario ID:** `{case_id}`
- **Underlying Evaluation Case ID:** `{eval_result.case_id}`
- **Execution Status:** `{eval_result.execution_status.value}`
- **Critical Failure Detected:** `{"YES ❌" if eval_result.has_critical_failure else "NO ✅"}`
- **Overall Case Passed:** `{"TRUE" if eval_result.passed else "FALSE"}`
"""

    # Format raw JSON result with clear scenario mapping metadata if applicable
    raw_dict = eval_result.model_dump()
    if case_id != eval_result.case_id:
        raw_dict = {"scenario_id": case_id, **raw_dict}
    import json
    raw_json_summary = json.dumps(raw_dict, indent=2)
    return workflow_md, checks_md, judge_md, verdict_md, raw_json_summary


def create_playground_app() -> Any:
    """Construct and return the Gradio Blocks application."""
    import gradio as gr

    with gr.Blocks(title="agent-eval-harness Evaluation Playground") as demo:
        gr.Markdown(
            """
            # 🧪 agent-eval-harness — Evaluation Playground
            **Offline Demonstration Mode:** This interactive interface runs pre-recorded,
            versioned fixtures and synthetic test cases through the core evaluation harness
            entirely offline. No live LLM calls, network access, or API keys are required.
            """
        )

        with gr.Row():
            with gr.Column(scale=1):
                scenario_dropdown = gr.Dropdown(
                    choices=get_available_scenarios(),
                    value=get_available_scenarios()[0],
                    label="Select Evaluation Scenario",
                )
                run_btn = gr.Button("▶ Run Evaluation", variant="primary")
                gr.Markdown(
                    """
                    ### About This Playground
                    - **Tier 1:** Deterministic checks (schema validation,
                      token leakage, channel rules, word counts).
                    - **Tier 2:** Rubric LLM judge (3 dimensions scored 1–4
                      with dimension-level veto).
                    - **Baseline Integrity:** Hermetic fixture replay
                      ensuring 100% reproducible outcomes.
                    """,
                    elem_id="sidebar-info",
                )

            with gr.Column(scale=3), gr.Tabs():
                with gr.TabItem("Workflow Execution"):
                    workflow_out = gr.Markdown("Select a scenario and click **Run Evaluation**.")
                with gr.TabItem("Tier 1: Deterministic Checks"):
                    checks_out = gr.Markdown("Deterministic check results will appear here.")
                with gr.TabItem("Tier 2: Rubric Judge"):
                    judge_out = gr.Markdown(
                        "Rubric judge scores and dimension veto analysis will appear here."
                    )
                with gr.TabItem("Final Verdict"):
                    verdict_out = gr.Markdown("Final evaluation verdict will appear here.")
                with gr.TabItem("Raw JSON Result"):
                    json_out = gr.Code(label="CaseEvaluationResult JSON", language="json")

        run_btn.click(
            fn=run_scenario,
            inputs=[scenario_dropdown],
            outputs=[workflow_out, checks_out, judge_out, verdict_out, json_out],
        )

        gr.Markdown(
            """
            ---
            *agent-eval-harness v0.1.0 • MIT License •
            [GitHub Repository](https://github.com/KishanR-dev/agent-eval-harness)*
            """
        )

    return demo


if __name__ == "__main__":
    app = create_playground_app()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False)
