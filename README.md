# agent-eval-harness

Offline, deterministic evaluation and regression-testing harness for a two-stage LLM agent workflow.

## Problem

LLM-powered agent pipelines are difficult to evaluate reproducibly. Model outputs are non-deterministic, provider APIs change, and semantic quality is hard to automate. Teams ship untested prompt changes, silently break guardrails, or claim quality improvements based on unreproduced metrics.

**agent-eval-harness** addresses this by separating what _can_ be tested deterministically from what _requires_ a language model to judge, and by making the deterministic tier the authoritative CI gate.

## Goals

- **Reproducibility:** Every evaluation result traces to a versioned dataset, schema, rubric, and execution mode.
- **Deterministic CI:** Pull request checks run offline, without API keys, network access, or provider SDKs.
- **Guardrail authority:** Critical deterministic failures (token leakage, contract violations, word count breaches) block the result regardless of semantic judge scores.
- **Evidence discipline:** No fabricated metrics, invented baselines, or unmeasured benchmark claims.

## Architecture

```
LeadInput (prospect context)
    │
    ▼
┌─────────────────────────┐
│  LeadQualificationAgent │──▶ LeadQualificationResult ──▶ OutreachHandoff
└─────────────────────────┘
    │                                                          │
    │  (DISQUALIFIED / NEEDS_REVIEW → skip Stage 2)            │
    │                                                          ▼
    │                                              ┌──────────────────────┐
    │                                              │ OutreachDrafterAgent │──▶ OutreachDraftResult
    │                                              └──────────────────────┘
    │                                                          │
    ▼                                                          ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       WorkflowCoordinator                             │
│  Routes lifecycle: COMPLETED │ SKIPPED_DISQUALIFIED │                 │
│    SKIPPED_NEEDS_REVIEW │ FAILED                                      │
│  Preserves Stage 1 artifacts on Stage 2 failure                      │
│  Translates AdapterError / ValidationError → structured FAILED       │
│  Unexpected programming bugs propagate uncaught                      │
└────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     Evaluation Pipeline                                │
│  1. Deterministic checks (CRITICAL_BLOCKING / WARNING)                │
│  2. Optional LLM judge (rubric-based, 1–4 discrete scale)            │
│  3. Baseline comparison (regression detection)                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Workflow stages

| Stage | Agent | Input | Output Contract |
| :--- | :--- | :--- | :--- |
| 1. Lead Qualification | `LeadQualificationAgent` | `LeadInput` | `LeadQualificationResult` → `OutreachHandoff` |
| 2. Outreach Drafting | `OutreachDrafterAgent` | `OutreachHandoff` | `OutreachDraftResult` |

All contracts are Pydantic v2 with `extra="forbid"`, `strict=True`, SemVer `1.0.0` schema versioning, and derived properties (`word_count`, `is_qualified`). Structural validation is kept strictly separate from business-policy rules (D-015, D-016).

### Provider-neutral adapter

Agents interact with language models exclusively through the `LLMAdapter` abstract protocol (`complete(prompt, system_prompt) → str`). The repository currently implements:

| Adapter | Purpose | Network Required |
| :--- | :--- | :--- |
| `FakeLLMAdapter` | Deterministic FIFO response queue + error injection for unit tests | No |
| `ReplayingLLMAdapter` | Sequential fixture playback with stage verification for integration tests | No |

**No live provider adapter exists.** Provider SDK dependencies (`google-genai`, `openai`, `anthropic`) are not installed. Live evaluation is formally deferred (D-022).

## Evaluation tiers

### Tier 1: Deterministic checks (authoritative)

Offline, reproducible, credential-free checks that run in CI on every pull request:

| Check | Severity | Tests |
| :--- | :--- | :--- |
| `check_lifecycle_status` | CRITICAL_BLOCKING | Coordinator status matches expected |
| `check_qualification_status` | CRITICAL_BLOCKING | Qualification enum matches expectation |
| `check_forbidden_leakage` | CRITICAL_BLOCKING | No planted tokens, competitor refs, or secrets in output |
| `check_score_bounds` | WARNING | Fit score within scenario-specific range |
| `check_channel_rules` | WARNING | EMAIL ↔ subject line, LINKEDIN ↔ no subject |
| `check_word_count_ceiling` | WARNING | Message body within word limit |
| `check_required_terms` | WARNING | Compliance keywords present |

A `CRITICAL_BLOCKING` failure unconditionally fails the evaluation case, regardless of judge scores.

### Tier 2: Rubric-based LLM judge (optional, subordinate)

Three dimensions on a discrete 1–4 scale:

- **relevance_positioning** — value proposition tailored to prospect context
- **factual_grounding** — claims derived from supplied context, no hallucinations
- **instruction_adherence** — tone, constraints, and channel etiquette beyond regex

**Pass policy:** All three dimensions must score ≥ 3 (dimension-level veto). `overall_score` and `passed` are derived in Python, not self-reported by the judge. An inconclusive or errored judge evaluation is never counted as a pass.

The judge is provider-neutral (uses `LLMAdapter`) and tested fully offline via `FakeLLMAdapter`. Untrusted content is wrapped in `<untrusted_evaluated_content>` XML boundaries with anti-injection instructions. These are engineering mitigations, not guarantees of LLM robustness.

### Tier 3: Baseline regression comparison

Compares current evaluation runs against reviewed baselines:

- **Canonical dataset hashing:** Deterministic SHA-256 digest over minified, sorted JSON. Identical datasets produce identical hashes regardless of whitespace or key ordering.
- **Compatibility key:** `(dataset_hash, schema_version, rubric_version, execution_mode)`. Any mismatch → `INCOMPATIBLE`.
- **Regression bifurcation:** Critical deterministic regressions (newly introduced `CRITICAL_BLOCKING` failures or coordinator crashes) are strictly separated from semantic regressions (judge score drops). Pre-existing failures do not trigger regression flags.
- **Standalone CLI** with deterministic exit codes: `0` clean, `1` regressions, `2` incompatible, `3` baseline missing, `4` invalid input.
- **Baselines are never auto-generated or silently overwritten.**

## Fixture replay

Offline, reproducible workflow execution uses versioned fixtures (`fixtures/*.json`) containing sequential recorded exchanges. Each fixture specifies a `call_index`, `stage`, and either a `response_text` or `error_to_raise` (mutual exclusion enforced).

`ReplayingLLMAdapter` replays these fixtures in FIFO order with optional stage-consistency verification. Fixture errors integrate seamlessly with coordinator failure handling.

Safety: fixtures require `is_synthetic=True` and are scanned for common credential patterns. Pattern scanning is a safeguard, not a guarantee.

**Canonical fixtures:**

| Fixture | Tests |
| :--- | :--- |
| `qualified_workflow.json` | Full 2-stage qualified path |
| `disqualified_workflow.json` | 1-stage skip path |
| `provider_error_workflow.json` | Stage 2 error with Stage 1 preservation |
| `workflow_with_judge.json` | 3-tier workflow + judge execution |

## Synthetic dataset

`datasets/synthetic_cases.json` contains **20 synthetic cases** serving as an offline smoke and regression test suite. Each case has a stable ID, scenario label, expected outcomes, and deterministic assertions.

**Limitations:**
- 20 cases are not a statistically representative benchmark. One case changes the aggregate rate by 5 percentage points.
- All data is synthetic. No real personal or company information.
- Deterministic replay checks verify token-signature absence in controlled fixtures, not real LLM resistance to prompt injection.

## Local setup (Windows / PowerShell)

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Install

```powershell
uv sync --all-extras --dev
```

### Launch Evaluation Playground (Optional UI)

```powershell
uv sync --extra playground --dev
.venv\Scripts\python src/agent_eval_harness/playground/app.py
```

### Run quality gates

```powershell
# Format check
.venv\Scripts\ruff format --check .

# Lint
.venv\Scripts\ruff check .

# Type check
.venv\Scripts\mypy src tests

# Tests with coverage enforcement (90% threshold)
.venv\Scripts\pytest --cov=agent_eval_harness --cov-report=term-missing --cov-fail-under=90 tests/

# Static secret scan
.venv\Scripts\python scripts/scan_secrets.py
```

All commands run offline without API keys, network access, or provider credentials.

### Baseline comparison CLI

```powershell
.venv\Scripts\python -m agent_eval_harness.evaluation.compare_cli --baseline path/to/baseline.json --current path/to/current.json
```

Options: `--strict` (fail on missing baselines), `--output path/to/report.json` (write structured result).

Exit codes: `0` clean, `1` regressions, `2` incompatible, `3` baseline missing, `4` invalid JSON/schema.

### Platform note

Development commands use Windows PowerShell path separators (`\`). On Linux/macOS or in CI, substitute forward slashes and use `uv run` (e.g., `uv run pytest ...`). The CI workflow (`.github/workflows/ci.yml`) runs on `ubuntu-latest` using `uv run`.

## CI

`.github/workflows/ci.yml` runs on every push to `main` and on pull requests targeting `main`:

1. Static secret scan
2. Ruff format check
3. Ruff lint
4. Mypy type check
5. Pytest with `--cov-fail-under=90`

**Permissions:** Read-only (`contents: read`). No provider credentials are injected. No live LLM calls are made. No external evaluation APIs are contacted.

## Current status

### Implemented and verified

| Item | Status | Tests | Stmt Coverage | Branch Coverage |
| :--- | :--- | :--- | :--- | :--- |
| 1. Pydantic v2 contracts | ✅ Accepted | 56 | 100% | 100% |
| 2. Agents + coordinator | ✅ Accepted | 88 | 100% | 100% |
| 3. Synthetic dataset + deterministic checks | ✅ Accepted | 128 | 100% | 100% |
| 4. Rubric-based LLM judge | ✅ Accepted | 162 | 100% | 100% |
| 5. Fixture record/replay | ✅ Accepted | 194 | 100% | 100% |
| 6. CI + baseline policy (Phases A–C) | ✅ Accepted | 248 | 100% (1049/1049) | 100% (282/282) |
| 8. README + repository closeout | Implemented & verified | 248 | 99.12% (1153/1161 stmts) | 98.41% (309/314 branches) |

### Formally deferred (D-022)

- **Live provider adapter:** No `AnthropicAdapter`, `GeminiAdapter`, or `OpenAIAdapter` exists. Provider SDKs are not installed.
- **Live evaluation workflow:** No manual GitHub Actions workflow for live LLM calls. Creating one without an executable adapter would produce a hollow, non-functional workflow.
- **Live baseline:** No committed baseline from a live model run. Baseline comparison tools operate against offline replay baselines or future authorized live runs.
- **Optional tracing (Item 7):** Langfuse integration is deferred. Core harness works without it.

### Provider feasibility assessment (D-022)

Official documentation for Google Gemini, OpenAI, and Anthropic Claude was verified on 2026-10-28. Key findings:

- Gemini's constrained decoding explicitly ignores `minLength`, `maxLength`, `minProperties`, `maxProperties`, and `uniqueItems` — client-side Pydantic validation remains mandatory.
- OpenAI Structured Outputs return refusals on safety boundaries and partial JSON on token truncation — not unconditional schema compliance.
- Anthropic uses tool-use definitions for structured output with similar truncation/refusal edge cases.
- Local credential audit: only `ANTHROPIC_API_KEY` is present locally; billing/quota is unverified. No CI secrets are configured.

See D-022 in `DECISIONS.md` for full provider evaluation details.

## Project structure

```
agent-eval-harness/
├── src/agent_eval_harness/
│   ├── contracts/          # Pydantic v2 inter-agent contracts (D-015, D-016)
│   ├── agents/             # LeadQualificationAgent, OutreachDrafterAgent
│   ├── providers/          # LLMAdapter protocol, FakeLLMAdapter, ReplayingLLMAdapter
│   ├── fixtures/           # Fixture schema models (ReplayFixture, RecordedExchange)
│   ├── evaluation/         # Dataset loading, checks, judge, rubric, runner, baseline, CLI
│   ├── coordinator.py      # WorkflowCoordinator (D-017)
│   └── exceptions.py       # Typed exception hierarchy
├── tests/                  # 248 offline deterministic tests
├── datasets/               # 20-case synthetic evaluation dataset
├── fixtures/               # Canonical replay fixtures (4 files)
├── scripts/                # Static secret scanner
├── .github/workflows/      # Deterministic CI workflow
├── SPEC.md                 # Architectural design and requirements
├── PLAN.md                 # Execution roadmap and phased strategy
├── CHECKLIST.md            # Task tracking with acceptance evidence
├── DECISIONS.md            # Dated architectural decision log (D-011 through D-022)
├── pyproject.toml          # Project configuration (Python 3.11, Pydantic v2, dev tools)
└── .env.example            # Environment variable template (placeholders only)
```

## Architectural decisions

The full decision log is in `DECISIONS.md`. Key entries:

| Decision | Summary |
| :--- | :--- |
| D-015 | Contract validation separated from business policy; strict Pydantic v2 without superficial `frozen=True` |
| D-016 | Single canonical `QualificationStatus` enum; no contradictory multi-field status |
| D-017 | Typed coordinator result with explicit status invariants; expected errors structured, bugs propagate |
| D-018 | Provider-neutral `LLMAdapter` protocol; deterministic `FakeLLMAdapter` |
| D-019 | Rubric judge with discrete 1–4 scale, dimension veto, deterministic derivation, fail-closed on errors |
| D-020 | Versioned fixtures, sequential replay, stage verification, credential pattern scanning |
| D-021 | Baseline contract, canonical hashing, strict regression bifurcation, immutable baselines |
| D-022 | Provider feasibility assessed; live evaluation formally deferred |

## Limitations

1. **Not a benchmark.** 20 synthetic cases provide smoke/regression coverage, not statistical significance.
2. **No live evaluation.** The harness currently operates entirely offline. Live provider evaluation requires implementing a concrete adapter, installing SDK dependencies, and establishing credentials.
3. **Deterministic checks are substring-based.** They detect planted token leakage and known patterns but cannot detect paraphrased, encoded, or novel data exfiltration.
4. **Judge scores are diagnostic.** LLM judge evaluations are non-deterministic, potentially biased, and subordinate to deterministic gates. Agreement across runs does not prove correctness.
5. **Fixture safety is bounded.** Regex credential scanning and `is_synthetic` flags are engineering safeguards, not mathematical guarantees.
6. **No tracing.** Langfuse or equivalent observability is deferred (Item 7).

## License

MIT
