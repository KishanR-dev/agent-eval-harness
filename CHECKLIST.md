# CHECKLIST.md — agent-eval-harness

Rules:
- Work sequentially and stop after the active item.
- Active scope: **Checklist Item 8**.
- Do not run future items early “for convenience.”
- Mark a checkbox complete only when evidence supports it.
- Record actual commands/results; never invent metrics.

## 1. Repository setup + inter-agent Pydantic contracts — TONIGHT ONLY

- [x] Inspect the existing repository state before changing files; preserve unrelated work.
- [x] Establish the minimal Python 3.11 project layout and dependency workflow using `uv` unless a concrete compatibility issue is found.
- [x] Configure Pydantic v2 contracts for lead-agent output, outreach-agent input/handoff, and outreach-agent output.
- [x] Include an explicit schema version and document the versioning approach.
- [x] Apply strict validation where intended; explicitly decide how unknown fields are handled.
- [x] Export JSON Schema and add a test that verifies export succeeds and includes expected top-level fields.
- [x] Add tests for valid payloads, missing required fields, wrong types, prohibited extra fields where applicable, and unsupported schema versions.
- [x] Ensure tests run locally using PowerShell-compatible commands and require no provider key or network access.
- [x] Add `.gitignore` protection for `.env`, virtual environments, caches, and generated artifacts as applicable; create `.env.example` with placeholders only if configuration files are introduced.
- [x] Check changed files for credentials, tokens, real personal/company data, and AI/tool co-author attribution.
- [x] Run the relevant tests and record the exact command, exit status, and actual test count.
- [x] Update `SPEC.md`, `PLAN.md`, `CHECKLIST.md`, and `DECISIONS.md` if implementation decisions differ from this plan.
- [x] Stop. Do not implement agents, coordinator, dataset, judge, fixtures, CI, tracing, or README polish in this item.

**Acceptance criteria**
- Contract models are Pydantic v2 and have documented boundaries and schema versioning.
- Contract tests cover valid and representative invalid payloads.
- JSON Schema export is tested.
- The targeted test command passes locally without API credentials or external network access.
- No secrets or real personal/company data are introduced.
- Existing work is preserved; no unrelated cleanup.
- Evidence report lists changed files, commands, outcomes, and limitations.
- Owner explicitly accepts item 1 before item 2 begins.

## 2. Agent implementations + lightweight coordinator

- [x] Implement lead qualification behavior against the agreed contract.
- [x] Implement outreach drafting behavior against the agreed contract.
- [x] Add a simple coordinator that validates each boundary and fails clearly on invalid handoffs.
- [x] Add a provider-neutral adapter interface and configuration validation without requiring a live key for unit tests; do not choose or integrate a concrete provider in this item.
- [x] Add tests using stubbed/fake providers.

**Acceptance criteria**
- Both agents obey contract boundaries.
- Invalid first-agent output never reaches the second agent as valid input.
- Unit tests do not call a live provider.
- Provider SDK code is isolated behind the adapter.
- Failure behavior and limitations are documented.

**Status: Accepted**
- 88 tests passed.
- 100% statement coverage: 337/337 statements.
- 100% branch coverage: 54/54 branches.
- Ruff format check, Ruff lint, and mypy all passed.
- The unreachable coordinator fallthrough was resolved by replacing the final `elif` with `else`, preserving the `FAILED` state invariants.
- No commit or push was performed.

## 3. Synthetic dataset + deterministic checks

- [x] Create a versioned synthetic dataset targeting 20 cases. If the time budget prevents 20 useful cases, record the actual count and reason rather than padding the dataset.
- [x] Label all records as fictional/synthetic; include stable IDs and expected assertions.
- [x] Implement deterministic schema, required/forbidden field, length, and explicitly defined guardrail checks.
- [x] Include planted synthetic-secret cases to test the specific leakage rule.
- [x] Document which risks are not deterministically detectable.

**Acceptance criteria**
- Every case has a stable ID and explicit expected behavior.
- No real people, companies, credentials, or sensitive records are present.
- Each deterministic check has positive and negative tests.
- Dataset size and limitations are stated accurately.
- No general claim of complete PII detection or truthfulness is made.

**Status: Accepted**
- 20 synthetic cases (`CASE-001` through `CASE-020`) in `datasets/synthetic_cases.json`.
- 128 tests passed.
- 100% statement coverage (554/554 statements).
- 100% branch coverage (122/122 branches).
- Ruff format check, Ruff lint, and mypy all passed.
- CASE-020 tests deterministic planted-token leakage detection across multi-stage outputs; it does not establish generalized LLM prompt-injection resistance.
- CASE-018 and CASE-019 use scenario-specific score bounds evaluated independently from qualification status, avoiding arbitrary qualification score cutoff assumptions.
- No commit or push was performed.

## 4. Rubric-based LLM judge

- [x] Define rubric dimensions and anchored score descriptions.
- [x] Separate judge results from deterministic guardrail results.
- [x] Record rubric version, model identifier, rationale, and run metadata.
- [x] Make judge execution optional and fail clearly when live configuration is missing.
- [x] Document known bias and variability.

**Acceptance criteria**
- Each rubric dimension has interpretable score anchors.
- Judge results are traceable to case, rubric version, model identifier, and run.
- Critical deterministic failures remain independently blocking.
- No unmeasured accuracy or judge reliability claims are published.
- Self-consistency checks remain deferred unless time and a specific question justify them.

**Status: Accepted**
- 162 tests passed.
- 100% statement coverage (729/729 statements).
- 100% branch coverage (170/170 branches).
- Ruff format check, Ruff lint, and mypy (34 source files) all passed.
- Implemented `RubricDimension`, discrete 1–4 scale anchors, and strict Pydantic v2 `DimensionScore`, `RawJudgeResponse`, and `JudgeVerdict` models.
- Exact dimension validation enforces that completed verdicts contain all 3 dimensions without omissions or duplicates.
- Python derives `overall_score` (arithmetic mean) and pass/fail verdicts; dimension-level veto enforces that all three dimensions must score >= 3 for `COMPLETED_PASS`.
- `JudgeVerdict.passed` is `None` when semantic evaluation is not applicable (`SKIPPED_NON_APPLICABLE`), ensuring unperformed evaluations are never reported as qualitative passes.
- A correctly skipped workflow (`SKIPPED_DISQUALIFIED` or `SKIPPED_NEEDS_REVIEW`) can pass its overall case if all applicable deterministic checks pass.
- Coordinator failures (`CoordinatorStatus.FAILED`) and critical deterministic failures (`CRITICAL_BLOCKING`) unconditionally fail the overall case.
- Defensive XML boundary framing (`<untrusted_evaluated_content>`) isolates untrusted prospect data; limits of prompt-injection mitigations documented.
- No commit or push was performed.

## 5. Fixture record/replay

- [x] Define a fixture format and safe recording policy.
- [x] Add replay support for provider responses.
- [x] Add tests for success, malformed fixture, missing fixture, and provider error paths.
- [x] Ensure deterministic CI runs replay offline.

**Acceptance criteria**
- Replay needs no API key and makes no network calls.
- Fixtures contain no secrets or real personal/company data.
- Replay validates the same contracts as live execution.
- Documentation distinguishes replay tests from live model evaluation.

**Status: Accepted**
- 194 tests passed (32 new tests added: 14 in `test_fixtures.py`, 14 in `test_replay_adapter.py`, 4 in `test_replay_workflow.py`).
- 100% statement coverage (836/836 statements).
- 100% branch coverage (196/196 branches).
- Ruff format check (46 files), Ruff lint (46 files), and mypy (40 source files) all passed with zero errors.
- Implemented strict Pydantic v2 fixture contracts (`ReplayFixture`, `RecordedExchange`, `ExchangeStage`) versioned at SemVer `1.0.0`.
- Sequential 0-indexed call tracking with mutual exclusion validation between `response_text` and `error_to_raise`.
- Credential pattern regex scan (`CREDENTIAL_PATTERN`) covering both `response_text` and `error_to_raise`, combined with synthetic flag enforcement (`is_synthetic=True`), with explicit documentation that regex scans and boolean flags are boundary safeguards, not mathematical guarantees of complete sanitization.
- Provider-neutral `ReplayingLLMAdapter(LLMAdapter)` implementing sequential FIFO playback, call history tracking (`AdapterCall`), cursor state, and strict stage consistency validation (`_detect_stage`) where both stage mismatches and unrecognized prompts fail explicitly with `AdapterError` when `verify_stage=True`.
- Distinguishable error taxonomy: `FixtureNotFoundError` (missing file), `FixtureCorruptedError` (JSON syntax / Pydantic validation failure), and `FixtureExhaustedError` (calls exceeding recorded exchanges; subclasses `AdapterError` to integrate into coordinator failure handling).
- Simulated provider errors raise `AdapterError(exchange.error_to_raise)` directly, seamlessly preserving coordinator failure routing and retaining prior valid stage results.
- Canonical synthetic fixtures: `fixtures/qualified_workflow.json` (2-stage qualified path), `fixtures/disqualified_workflow.json` (1-stage skip path), `fixtures/provider_error_workflow.json` (2-stage path simulating Stage 2 provider error and proving Stage 1 result retention), and `fixtures/workflow_with_judge.json` (3-tier workflow + judge path).
- Unit and end-to-end integration tests verify coordinator lifecycle routing, state preservation, and 3-tier workflow + judge execution using replay fixtures loaded directly from disk.
- No commit or push was performed.

## 6. CI workflows + baseline policy

- [x] Add required GitHub Actions workflow on `ubuntu-latest`.
- [x] Run contract tests, deterministic guardrails, fixture replay, and selected static checks.
- [ ] Add manual live-evaluation workflow only if the core scope is stable. *(Formally deferred per D-022: no live adapter or CI credentials exist; avoids hollow workflow).*
- [x] Define baseline metadata and compatibility checks.
- [x] After the adapter and live path are stable, select a concrete provider based on verified access, model availability, quota, SDK compatibility, and reproducibility metadata. *(Feasibility assessed for Gemini, OpenAI, and Anthropic in D-022; implementation deferred).*
- [ ] Attempt one real live evaluation and establish/commit a measured baseline if feasible within the overall 10–12 hour budget. *(Formally deferred per D-022).*
- [x] If a live run/baseline is infeasible, document the concrete blocker and mark it deferred; do not invent results or claim baseline regression gating is operational.
- [ ] Establish and commit a baseline only from an actual run with explicit review. *(Preserved: unestablished/deferred; zero fabricated baselines).*
- [x] Add secret scanning if integration is proportionate and reliable.
- [x] Review permissions and secret exposure; do not expose secrets to untrusted fork PRs.

**Acceptance criteria**
- Required PR CI passes without API keys or live LLM calls.
- A deliberate deterministic regression causes a clear failure.
- Live workflow is opt-in and secret-safe.
- Baseline is not auto-generated or silently updated.
- Provider choice is justified by verified constraints rather than assumed in advance.
- A live run and baseline are either evidenced by a real run or explicitly deferred with the blocker documented.
- Any committed baseline contains reproducibility metadata.
- README metrics match actual run artifacts.

**Phase A Status: Implemented & Verified**
- GitHub Actions deterministic CI workflow `.github/workflows/ci.yml` on `ubuntu-latest` with read-only permissions (`contents: read`).
- Workflow executes bounded secret scanner, Ruff format check, Ruff lint, mypy type-checking, and pytest with `--cov-fail-under=90`. Validated with `actionlint` (0 errors).
- Static secret scanner `scripts/scan_secrets.py` with strict log redaction and zero false positives.

**Phase B Status: Implemented & Verified**
- Implemented `src/agent_eval_harness/evaluation/baseline.py`: canonical dataset hashing (`compute_dataset_hash`), strict Pydantic v2 `RunMetadata`, `BaselineRecord`, and `compare_against_baseline`.
- Canonical dataset hashing produces a deterministic SHA-256 digest of minified, key-sorted, case-id-sorted JSON representations, ensuring formatting and newline invariance.
- Multi-factor compatibility key `(dataset_hash, schema_version, rubric_version, execution_mode)` enforces run comparability.
- Strict regression bifurcation: `critical_deterministic_regressions` tracks newly introduced failing critical guardrails (`CRITICAL_BLOCKING`) and coordinator execution failures (`CoordinatorStatus.FAILED`). Pre-existing failures present in both runs are tracked as unchanged and do not trigger regression flags. `semantic_regressions` tracks rubric dimension score drops below pass threshold (score < 3) and judge status regressions. Semantic score drops are strictly excluded from critical regressions.
- Implemented standalone comparison CLI `src/agent_eval_harness/evaluation/compare_cli.py` with deterministic exit codes (0: clean, 1: regressions, 2: incompatible, 3: baseline missing, 4: invalid JSON/schema).
- Added 45 new tests across `tests/test_baseline.py` and `tests/test_regression_demonstration.py`, demonstrating deliberate planted token leakage, word count ceiling breaches, semantic score drops, coordinator failures, pre-existing failure neutrality, and all CLI exit codes.
- 239 tests passed; 100% statement coverage (1049/1049) and 100% branch coverage (282/282).

**Phase C Status: Implemented & Verified (Provider Feasibility Assessment & Documented Deferral)**
- Verified current official documentation (checked 2026-10-28) for Google Gemini (`https://ai.google.dev/gemini-api/docs/models/gemini`, `https://ai.google.dev/gemini-api/docs/structured-output`, `https://ai.google.dev/pricing`), OpenAI (`https://developers.openai.com/api/docs/models`, `https://developers.openai.com/api/docs/guides/structured-outputs`, `https://developers.openai.com/api/docs/pricing`), and Anthropic (`https://platform.claude.com/docs/en/models/overview`, `https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview`, `https://platform.claude.com/docs/en/about-claude/pricing`).
- Verified exact model identifiers and operational statuses: Gemini (`gemini-3.8-flash` New Stable, `gemini-3.6-flash` Stable, `gemini-3.5-flash-lite` Stable, `gemini-4-argon` New Stable, `gemini-2.5-flash` active restricted); OpenAI (`gpt-4o-mini`, `gpt-4o`, `gpt-6-astra`); Anthropic (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-1`, `claude-haiku-4-5-20251001`).
- Qualified structured-output mechanisms: Gemini supports JSON schema decoding via `response_format` but its grammar engine explicitly ignores and strips `minLength`, `maxLength`, `minProperties`, `maxProperties`, and `uniqueItems`; OpenAI supports native strict JSON Schema via `response_format={"type": "json_schema", "json_schema": {"strict": true}}` but returns refusals on safety boundaries and partial JSON on token truncation; Anthropic uses structured tool calling (`tools` + `tool_choice`). Crucially, provider-level output constraints only govern format/syntax at sampling time; client-side Pydantic validation and deterministic checks remain independent, mandatory, and authoritative for all business rules, word caps, and field validation.
- Pricing & authentication: Gemini published pricing provides a free tier for standard text on 3.8 Flash, 3.6 Flash, and 3.5 Flash-Lite subject to RPM/TPM limits; OpenAI and Anthropic require pre-funded platform credits with no ongoing free API tier. Safe credential audit confirmed `GEMINI_API_KEY`, `GOOGLE_API_KEY`, and `OPENAI_API_KEY` are `NOT_SET`. `ANTHROPIC_API_KEY` is `SET_NON_EMPTY` locally, but not configured as a GitHub Actions secret for CI, and presence does not imply active quota or valid billing; no live API calls were made.
- Audited codebase and dependencies: confirmed only `LLMAdapter` (protocol), `FakeLLMAdapter`, and `ReplayingLLMAdapter` exist in `src/agent_eval_harness/providers/`; zero live provider adapters and zero provider SDKs (`google-genai`, `openai`, `anthropic`) exist in `pyproject.toml`.
- Recorded `D-022` in `DECISIONS.md`: formally deferred live evaluation and live-baseline creation to avoid hollow workflows, broken CI, or fabricated metrics. Deterministic CI remains 100% offline, credential-free, and authoritative.


## 7. Optional tracing

- [ ] Reassess whether Langfuse adds value within the remaining time.
- [ ] If approved, add local Docker Compose configuration and minimal tracing.
- [ ] Keep tracing disabled in deterministic CI.
- [ ] Review traces for secrets and unnecessary prompt/data exposure.

**Acceptance criteria**
- Core tests and CI work without Langfuse.
- Tracing is explicitly opt-in.
- No secrets are emitted in traces.
- Setup and teardown instructions are documented.
- If time is insufficient, document as deferred rather than partially claiming completion.

## 8. README + controlled regression demo

- [x] Document project purpose, architecture, PowerShell quickstart, deterministic/live tiers, limitations, and roadmap.
- [x] Publish only measured results with date, commit SHA, dataset version, model identifier where relevant, and configuration.
- [x] Create a controlled demo branch or test that causes an intended check to fail. *(Demonstrated via 13 offline tests in `tests/test_regression_demonstration.py` covering planted token leakage, word count ceiling breaches, semantic score drops, coordinator failures, and CLI exit codes 0–4 without requiring a premature Git commit).*
- [x] Check repository files, commit messages, and trailers for AI/tool co-author attribution before commit/push.
- [x] Review all docs for invented metrics, secrets, misleading benchmark claims, and unsupported reliability claims.

**Acceptance criteria**
- A new reader can run deterministic checks without an API key.
- All reported results are reproducible from identified evidence.
- Demo regression fails for the documented reason without corrupting the normal baseline.
- No secrets or prohibited attribution are introduced.
- Deferred features and known limitations are explicit.

**Status: Implemented & Verified (Pending Reviewer Acceptance)**
- 239 tests passed; 100% statement coverage (1049/1049) and 100% branch coverage (282/282).
- Ruff format check (53 files), Ruff lint (53 files), mypy type-checking (45 source files), and static secret scanning (57 files) all passed.
- Successfully executed `uv sync --all-extras --dev` (exit code 0).
- Baseline comparison CLI verified (`compare_cli.py` tested for all exit codes 0–4).
- `README.md` rewritten with comprehensive architecture, setup, evaluation tiers, fixture replay, CI workflow, decisions summary, and explicit limitations.
- Reconciled tracking across `SPEC.md`, `PLAN.md`, `CHECKLIST.md`, and `README.md` to distinguish implementation completion from formal reviewer acceptance.
- Preserved zero AI/tool attribution, zero committed secrets, and untouched `agent-eval-harness-docs.zip`.
- No commit or push was performed.
