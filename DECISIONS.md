# DECISIONS.md — decision log

## Status

Initial review of the draft. These decisions guide implementation unless the project owner explicitly changes them.

## D-001 — Deterministic CI is the primary required gate
- **Decision:** Every PR must run an offline, API-key-free deterministic tier.
- **Draft change:** Clarifies that live LLM evaluation is not a required PR check.
- **Rationale:** Required checks should be repeatable and available to contributors without provider credentials.
- **Consequences:** Fixtures and deterministic assertions are core scope, not optional extras.

## D-002 — Treat 20 cases as a smoke/regression set
- **Decision:** A 20-case synthetic dataset may be used initially, but must not be described as representative or statistically sufficient.
- **Draft change:** Adds explicit limits and requires counts plus percentages.
- **Rationale:** With 20 equally weighted binary cases, each case changes the aggregate by 5 percentage points.
- **Consequences:** Expand based on observed failure modes when feasible; avoid broad reliability claims.

## D-003 — Deterministic guardrails are independent of judge scores
- **Decision:** Critical deterministic guardrail failures block independently of aggregate scores.
- **Draft change:** Prevents an improved average judge score from masking a critical failure.
- **Rationale:** Safety/contract properties should not be traded away by a weighted aggregate.
- **Consequences:** Keep deterministic and judge results separately visible.

## D-004 — Judge scores are diagnostic, not ground truth
- **Decision:** Use an anchored rubric and store rationale/metadata, but document judge bias and variability.
- **Draft change:** Self-consistency is deferred from the initial must-have scope.
- **Rationale:** Repeated agreement does not establish correctness and costs additional calls.
- **Consequences:** Do not publish unsupported judge reliability claims.

## D-005 — Baselines require a real run and explicit review
- **Decision:** Never invent, automatically refresh, or silently overwrite a baseline.
- **Draft change:** Requires run metadata and a reviewed commit.
- **Rationale:** A regression comparison is meaningful only when its reference run is identifiable and compatible.
- **Consequences:** Report baseline-unavailable state explicitly; never claim a gate exists before it is configured.

## D-006 — Start with a lightweight coordinator; defer LangGraph
- **Decision:** Use plain Python orchestration for the two-stage sequential workflow.
- **Draft change:** LangGraph is no longer an initial requirement.
- **Rationale:** The current workflow does not yet establish a need for graph state, branching, checkpointing, or recovery.
- **Revisit when:** A concrete requirement needs those capabilities and the added dependency is justified.

## D-007 — Defer Langfuse
- **Decision:** Use structured run metadata and JSONL artifacts first; tracing remains optional.
- **Draft change:** Langfuse and Docker Compose move out of the critical path.
- **Rationale:** Local infrastructure adds setup and maintenance overhead without being necessary to prove the core gate.
- **Revisit when:** Trace inspection addresses a demonstrated debugging or portfolio requirement.

## D-008 — Start live evaluation with manual dispatch
- **Decision:** Use `workflow_dispatch` before considering PR-label-triggered live runs.
- **Draft change:** PR label triggering is deferred pending permission and secret-exposure review.
- **Rationale:** Manual execution is simpler to secure and control initially.
- **Consequences:** Live evaluation is opt-in and never exposes secrets to untrusted fork PRs.

## D-009 — Tonight is checklist item 1 only
- **Decision:** First session scope is repository baseline/setup and Pydantic contract tests only.
- **Draft change:** Makes the stop condition explicit and prohibits advancing to agent implementation or later checklist items.
- **Rationale:** Small accepted increments reduce scope drift and make review evidence clear.
- **Consequences:** Stop after item 1 and wait for owner acceptance.

## D-010 — No invented metrics or unsupported benchmark claims
- **Decision:** All reported numbers must come from actual execution and identifiable evidence.
- **Draft change:** Applies to README, reports, baselines, and agent status summaries.
- **Rationale:** Evidence integrity is a core portfolio quality signal.
- **Consequences:** Mark unknowns as unknown; record skipped tests and unverified assumptions honestly.

## D-011 — Repository attribution hygiene
- **Decision:** Do not introduce AI/tool co-author attribution in commits or repository content. Inspect commit messages, trailers, and files before commit/push.
- **Draft change:** Adds an explicit acceptance check.
- **Rationale:** Maintains the owner's repository presentation requirements.
- **Consequences:** Preserve existing published history; do not rewrite or force-push history to remove prior attribution without explicit authorization.


## D-012 — Keep the provider adapter neutral until live-provider selection
- **Decision:** Define the adapter boundary first and defer the concrete provider choice until the offline harness is stable.
- **Owner confirmation:** The project owner selected “provider adapter first; choose provider later.”
- **Draft change:** Removes Gemini as an assumed default provider; provider selection is based on verified access, model availability, quota, SDK compatibility, and reproducibility metadata.
- **Rationale:** Prevents early coupling and avoids assuming free-tier access or a stable model identifier before verification.
- **Consequences:** Item 1 must not integrate a provider SDK. Live provider selection happens later and must be documented.

## D-013 — Target 20 synthetic cases without treating them as a quality benchmark
- **Decision:** Aim for 20 useful, versioned synthetic cases for the initial dataset.
- **Owner confirmation:** The owner selected the 20-case target with an explicit no-benchmark interpretation.
- **Draft change:** “20 cases if time allows” becomes a target; if time prevents completion, document the actual count and reason rather than padding the dataset.
- **Rationale:** The set is intended for smoke/regression coverage, not a statistically representative quality claim.
- **Consequences:** Report case counts and observed results honestly; do not infer broad reliability from the aggregate.

## D-014 — Prefer a real live evaluation and measured baseline if feasible
- **Decision:** Include a real live evaluation and measured baseline in the 10–12 hour plan if provider access, quota, implementation stability, and remaining time allow.
- **Owner confirmation:** The owner prioritized attempting a real live run and measured baseline where feasible.
- **Draft change:** Live evaluation/baseline are preferred deliverables rather than automatically deferred, but are not allowed to compromise deterministic CI or evidence integrity.
- **Rationale:** A real measured run strengthens the demonstration of the evaluation workflow, provided it is genuinely executed and traceable.
- **Consequences:** After the offline harness is stable, choose a provider based on verified constraints, run the live workflow, review results, and commit the baseline explicitly. If infeasible, document the concrete blocker and leave the baseline unestablished. Never invent results or claim regression gating is operational without a compatible baseline.

## D-015 — Contract validation and business-rule separation
- **Decision:** Use Pydantic v2 contracts with strict validation where intended, reject unexpected fields by default (`extra="forbid"`), and explicitly version schemas via SemVer represented both in types/JSON Schema (`Literal`) and runtime validation. Prefer removing `frozen=True` for this initial contract layer because top-level attribute freezing does not provide deep immutability or thread safety for mutable collection fields (such as `list[str]`). Keep structural validation distinct from business-policy rules. Avoid redundant derived fields unless a documented consumer requirement justifies them; derive properties (e.g. `word_count`) in Python rather than demanding them in payload schemas. Do not silently normalize contract values globally (no global whitespace stripping).
- **Rationale:** Contracts should enforce agreed interface requirements without silently turning arbitrary example thresholds or workflow assumptions into universal policy. Superficial freezing without deep immutability creates a false sense of thread safety.
- **Consequences:** Unsupported schema versions must be rejected reliably both at runtime and as encoded constraints in exported JSON Schema; cross-field rules require documented justification and tests; word counts are derived from message body; whitespace rejection is validated on specific fields where required.

## D-016 — Qualification classification consistency
- **Decision:** The lead qualification contract must have an unambiguous representation of qualification status. Use a single canonical classification field (`qualification_status: QualificationStatus` with values `QUALIFIED`, `DISQUALIFIED`, `NEEDS_REVIEW`) and expose helper properties (`is_qualified`) without duplicating status fields in the payload. Structural validation must remain separate from business-policy checks.
- **Rationale:** Contradictory qualification fields can make downstream evaluation results difficult to interpret and undermine reproducibility.
- **Consequences:** Avoid arbitrary score thresholds in structural validation. Document any intentional deferral of cross-field consistency checks (e.g. alignment between fit score and qualification status) to the evaluation runner layer.

## D-017 — Coordinator failure semantics, state invariants, and non-qualified routing
- **Decision:** The workflow coordinator emits a strictly typed `CoordinatorResult` with explicit `CoordinatorStatus` values (`COMPLETED`, `SKIPPED_DISQUALIFIED`, `SKIPPED_NEEDS_REVIEW`, `FAILED`). It enforces state integrity invariants via model-level validation (e.g., `COMPLETED` requires all stage artifacts and forbids failure fields; skipped states require matching non-qualified lead status and forbid handoff/draft; `FAILED` requires failure diagnostic fields and forbids draft result while preserving prior valid stage artifacts). Leads with `DISQUALIFIED` or `NEEDS_REVIEW` halt without invoking the Stage 2 outreach agent. Only explicitly expected adapter errors (`AdapterError`) and contract validation errors (`ValidationError`) are translated into structured failures; unexpected programming bugs (`TypeError`, `KeyError`, `RuntimeError`) propagate uncaught.
- **Rationale:** Swallowing unexpected errors produces silent failures and corrupts evaluation integrity. Strict invariants guarantee downstream evaluators never observe contradictory workflow output states.
- **Consequences:** Callers and evaluation runners can rely on deterministic status invariants. Diagnostics preserve intermediate stage outputs on Stage 2 failures.

## D-018 — Provider-neutral adapter abstraction and deterministic fake
- **Decision:** Decouple agent prompt execution from provider SDKs using a lightweight `LLMAdapter` abstract base class with a standardized `complete(prompt, system_prompt)` interface and `AdapterCall` history recording. Provide `FakeLLMAdapter` as an offline, deterministic FIFO response queue supporting exact string responses, queue exhaustion checks, and deterministic exception injection.
- **Rationale:** Avoids premature vendor coupling, eliminates external network dependencies and costs from automated test suites, and enables reproducible testing in isolated CI environments.
- **Consequences:** All unit and integration tests run offline without network access or credentials. Future live provider implementations (e.g., Gemini, OpenAI, Anthropic) can be introduced as clean adapter subclasses without altering agent or coordinator logic.

## D-019 — Rubric-based judge design, discrete 1–4 scale, and deterministic authority
- **Decision:** Define a provider-neutral semantic evaluation tier using `LLMJudge` built on `LLMAdapter`. The judge evaluates three canonical dimensions (`relevance_positioning`, `factual_grounding`, `instruction_adherence`) on a discrete 1 to 4 ordinal scale. The judge LLM outputs only dimension-level scores and rationales; `overall_score` (arithmetic mean) and `passed` status are derived deterministically in Python to prevent self-contradictory evaluator outputs. A case passes semantic evaluation if and only if all three dimensions score >= 3 (dimension-level veto). A critical deterministic failure unconditionally fails the case, taking total precedence over judge scores. Similarly, coordinator execution failures (`CoordinatorStatus.FAILED`) produce `JudgeStatus.WORKFLOW_FAILED` and unconditionally fail the overall case. Outcomes explicitly separate quality failures (`COMPLETED_FAIL`) from parsing defects (`INCONCLUSIVE_OUTPUT`), adapter/provider errors (`EXECUTION_ERROR`), non-applicable workflows (`SKIPPED_NON_APPLICABLE`), and workflow failures (`WORKFLOW_FAILED`). For non-applicable workflows (`SKIPPED_NON_APPLICABLE`), `JudgeVerdict.passed` returns `None` (not `True`) so that an unexecuted semantic check is never counted as a passing qualitative evaluation, while the runner allows the overall case to pass if all deterministic expectations pass. Untrusted inputs are defensively enclosed in XML boundaries with explicit anti-injection evaluator instructions.
- **Rationale:** Prevents middle-score bias, prevents hallucinated drafts from passing due to high arithmetic averages, guarantees that infrastructure or parser failures are not misattributed as agent quality regressions, prevents conflating unexecuted semantic evaluations with passing grades, and ensures hard deterministic contracts and security guardrails remain authoritative.
- **Consequences:** All judge tests execute 100% offline via `FakeLLMAdapter`. Deterministic CI remains credential-free and network-free. Failed workflows cannot produce passing evaluation cases. Live provider selection and live baseline experiments remain strictly opt-in and deferred from core CI.

## D-020 — Fixture record/replay format, sequential playback, and safety boundaries
- **Decision:** Define a standardized offline replay fixture format using strict Pydantic v2 contracts (`ReplayFixture`, `RecordedExchange`, `ExchangeStage`) versioned at SemVer `1.0.0`. Exchanges are strictly 0-indexed and sequential. Mutual exclusion is enforced between `response_text` and `error_to_raise`. Provider-neutral `ReplayingLLMAdapter` implements `LLMAdapter` with FIFO playback, call tracking (`AdapterCall`), and cursor state. Stage consistency verification (`_detect_stage`) checks the incoming prompt against the recorded exchange stage without altering the `complete(prompt, system_prompt)` interface; when `verify_stage=True`, both stage mismatches and unrecognized prompt signatures fail explicitly with `AdapterError` to prevent silent stage bypass. The error taxonomy cleanly distinguishes `FixtureNotFoundError` (missing file), `FixtureCorruptedError` (syntax/validation failure), and `FixtureExhaustedError` (calls exceeding exchanges; subclasses `AdapterError` to integrate with coordinator failure handling). Simulated provider errors raise `AdapterError(exchange.error_to_raise)` directly. Fixture safety combines synthetic provenance flags (`is_synthetic=True`) with lightweight regex pattern scanning (`CREDENTIAL_PATTERN`) covering both `response_text` and `error_to_raise`, with explicit documentation that regex scans and boolean flags are boundary safeguards, not mathematical guarantees of complete sanitization.
- **Rationale:** Ensures deterministic test execution and regression replay without API keys, live costs, or external network dependencies; detects call sequencing drift and prompt tampering early; preserves coordinator failure taxonomy and stage 1 artifact retention; and clearly sets boundaries on sanitization guarantees.
- **Consequences:** All replay tests run offline in CI. Stage mismatch, unrecognized prompts under verification, or exhaustion raises clear, typed exceptions. Fixtures cannot contain common secret patterns like API keys or JWTs in responses or simulated errors without triggering validation errors.

## D-021 — Baseline record contract, canonical hashing, regression taxonomy, and comparison policy
- **Decision:** Establish an offline, reproducible baseline record and regression comparison framework governed by immutable Pydantic v2 contracts (`BaselineRecord`, `RunMetadata`, `BaselineComparisonResult`). Canonical dataset hashing (`compute_dataset_hash`) generates a deterministic SHA-256 digest of minified, key-sorted, case-id-sorted JSON representations, ensuring byte-level invariance across whitespace, formatting, line endings, and file ordering. Comparisons enforce a multi-factor compatibility key `(dataset_hash, schema_version, rubric_version, execution_mode)`; any divergence produces a structured `INCOMPATIBLE` outcome (or raises `BaselineIncompatibleError` in strict mode). Replay execution metadata strictly requires `model_id is None` or `'offline-replay'`, preventing offline runs from falsely claiming live model evaluation. Uncommitted repository runs record `commit_sha=None`; no synthetic or fake commit SHAs are fabricated for real runs. Invariants enforce strict consistency: `total_cases == len(case_results) == pass_count + fail_count`, with `pass_rate` and `case_id` alignment mathematically verified. Regressions are strictly bifurcated: `critical_deterministic_regressions` tracks newly introduced failing critical guardrails (`CRITICAL_BLOCKING`) and coordinator execution failures (`CoordinatorStatus.FAILED`) where the failure was not already present in the baseline (pre-existing failures present in both runs are tracked as unchanged and do not trigger regression flags), while `semantic_regressions` tracks rubric dimension score drops below the passing threshold (score < 3) and judge status regressions. Semantic score changes are strictly barred from being placed in `critical_deterministic_regressions`. A standalone, deterministic CLI (`compare_cli.py`) evaluates baseline records with unambiguous exit codes (0: clean, 1: regressions, 2: incompatible, 3: baseline missing, 4: invalid JSON/schema). Baselines are strictly immutable committed artifacts; CI and comparator tools never automatically overwrite, mutate, or regenerate baselines. Baseline comparison is delivered as an executable comparison engine and CLI for developer workflows and manual gating; it is not hooked as an automated CI blocker without an approved, committed baseline.
- **Rationale:** Prevents silent baseline drift and self-fulfilling test suites; prevents misclassifying qualitative semantic score drops as critical security or integrity violations; guarantees dataset identity across environments; and preserves reproducible evaluation auditability.
- **Consequences:** Developers and evaluators can detect regressions deterministically with exact score deltas. Replay mode and live mode cannot be conflated. Strict separation ensures critical guardrail breaches immediately fail gating while semantic shifts provide actionable diagnostic feedback.

## D-022 — Provider feasibility assessment, structured-output constraints, and live evaluation deferral
- **Decision:** Conduct a rigorous feasibility assessment of official LLM provider APIs (Google Gemini, OpenAI, Anthropic Claude), qualify their supported structured-output mechanisms and constraints against official documentation, and formally defer live model evaluation, live baseline establishment, and manual live GitHub Actions workflows. The offline deterministic test suite, fixture replay adapter (`ReplayingLLMAdapter`), and baseline comparison CLI (`compare_cli.py`) remain the authoritative evaluation harness.
- **Provider Evaluation Findings (Checked 2026-10-28):**
  1. **Google Gemini:**
     - *Official Sources:* Model listing at `https://ai.google.dev/gemini-api/docs/models/gemini`, structured outputs at `https://ai.google.dev/gemini-api/docs/structured-output`, pricing at `https://ai.google.dev/pricing`.
     - *Verified Exact Model Identifiers & Operational Status:*
       - `gemini-3.8-flash`: Status `"New Stable"` (Generally Available)
       - `gemini-3.6-flash`: Status `"Stable"` (Generally Available)
       - `gemini-3.5-flash-lite`: Status `"Stable"` (Generally Available)
       - `gemini-4-argon`: Status `"New Stable"` (Generally Available)
       - `gemini-2.5-flash`: Status `"Active (Restricted access to prior users; not deprecated)"`
     - *Structured-Output Mechanism & Limitations:* Employs `response_format={"type": "text", "mime_type": "application/json", "schema": ...}`. Supports basic types (`object`, `array`, `string`, `number`, `integer`, `boolean`), object `properties`/`required`/`additionalProperties`, string `enum`/`format`, number `minimum`/`maximum`, and array `minItems`/`maxItems`. However, the constrained decoding grammar engine explicitly ignores and strips `minLength`, `maxLength`, `minProperties`, `maxProperties`, `uniqueItems`, `contains`, `minContains`, and `maxContains`. Furthermore, schemas with high branching or state complexity can fail with `400 INVALID_ARGUMENT`. String length and collection constraints are not enforced server-side and must be checked client-side.
     - *Authentication, Pricing & Rate Limits:* Authenticates via `x-goog-api-key` header or `GEMINI_API_KEY`/`GOOGLE_API_KEY` env vars. Published pricing provides a "Free of charge" tier for standard inputs and outputs on select models (`gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`), subject to published RPM/TPM limits and regional availability. `gemini-4-argon` has no free tier ($2.00/MTok input, $10.00/MTok output). Safe local environment audit confirmed `GEMINI_API_KEY` and `GOOGLE_API_KEY` are not configured (`NOT_SET`).
  2. **OpenAI:**
     - *Official Sources:* Model listing at `https://developers.openai.com/api/docs/models`, structured outputs at `https://developers.openai.com/api/docs/guides/structured-outputs`, pricing at `https://developers.openai.com/api/docs/pricing`.
     - *Verified Exact Model Identifiers & Operational Status:*
       - `gpt-4o-mini`: Status Available / Supported in Structured Outputs guide & Pricing
       - `gpt-4o`: Status Available / Supported in Structured Outputs guide (snapshot `gpt-4o-2024-08-06`) & Pricing
       - `gpt-6-astra`: Status Available / Flagship model listed in Models page and recommended for Structured Outputs in new software
     - *Structured-Output Mechanism & Limitations:* Employs native `response_format={"type": "json_schema", "json_schema": {"name": "...", "strict": true, "schema": ...}}`. Requires all object fields to be in `required` and `additionalProperties: false`. Does not provide unconditional schema compliance: requests triggering safety boundaries return a `refusal` string rather than the JSON schema payload, and output truncated by `max_output_tokens` or context limits will be incomplete or invalid JSON.
     - *Authentication, Pricing & Rate Limits:* Authenticates via `Authorization: Bearer $OPENAI_API_KEY`. Published pricing documents no free API tier for these models (standard rates: `gpt-4o-mini` at $0.15/MTok input, $0.60/MTok output; `gpt-4o` at $2.50/MTok input, $10.00/MTok output; `gpt-6-astra` at $10.00/MTok input, $50.00/MTok output). API calls require pre-funded account credits; rate limits scale with organization usage tier. Safe local environment audit confirmed `OPENAI_API_KEY` is not configured (`NOT_SET`).
  3. **Anthropic Claude:**
     - *Official Sources:* Models overview at `https://platform.claude.com/docs/en/models/overview`, tool use guide at `https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview`, pricing at `https://platform.claude.com/docs/en/about-claude/pricing`.
     - *Verified Exact Model Identifiers & Operational Status:*
       - `claude-haiku-5-5`: Status Available / Generally Available (Retirement: Not sooner than October 7, 2027)
       - `claude-sonnet-5-5`: Status Available / Generally Available (Retirement: Not sooner than September 28, 2027)
       - `claude-opus-5-5`: Status Available / Generally Available (Retirement: Not sooner than September 22, 2027)
       - `claude-fable-5-1`: Status Available / Generally Available (Retirement: Not sooner than September 1, 2027)
       - `claude-haiku-4-5-20251001`: Status Available (Legacy model snapshot `claude-haiku-4-5`)
     - *Structured-Output Mechanism & Limitations:* Structured outputs are elicited via tool use definitions (`tools=[{"name": "...", "input_schema": ...}]`). Enforcing output requires setting `tool_choice={"type": "tool", "name": "..."}` or `strict: true`. The model returns a structured `tool_use` block whose input must be parsed as JSON. Output generation halted by token limits or safety rejections will emit truncated blocks or error stops.
     - *Authentication, Pricing & Rate Limits:* Authenticates via `x-api-key: $ANTHROPIC_API_KEY`. Published pricing documents no ongoing free API tier for programmatic Messages API calls (standard rates: `claude-haiku-5-5` from $0.10/MTok input, $0.50/MTok output; `claude-sonnet-5-5` at $2.00/MTok input, $10.00/MTok output; `claude-opus-5-5` at $4.00/MTok input, $20.00/MTok output). Account requires pre-funded platform credits; rate limits scale by organization usage tier. Safe local environment audit revealed `ANTHROPIC_API_KEY` is present in the local user environment (`SET_NON_EMPTY`), but it is not configured as a GitHub Actions secret for CI, and local environment-variable presence does not imply valid authorization, active quota, or usable billing standing. No live API calls were executed.
- **Distinction Between Provider Constraints and Harness Validation:**
  Provider-level constrained decoding or tool-use enforcement operates strictly at generation/sampling time to constrain JSON syntax or schema keys. Provider mechanisms cannot verify:
  1. Client-side field validations that providers explicitly strip or ignore (e.g. Gemini stripping `minLength` and `maxLength`).
  2. Cross-field consistency (e.g. fit score alignment with qualification status enum).
  3. Domain business policy (e.g. email word count caps, channel matching).
  4. Non-schema model rejections (e.g. OpenAI refusals, token truncation).
  Therefore, the harness's client-side Pydantic contracts and deterministic evaluation suite remain independent, mandatory, and authoritative gates regardless of provider-level capabilities.
- **Repository Architecture Findings:**
  1. The codebase currently implements only `LLMAdapter` (protocol), `FakeLLMAdapter`, and `ReplayingLLMAdapter` in `src/agent_eval_harness/providers/`. No live provider adapter exists.
  2. The dependency manifest (`pyproject.toml`) contains only `pydantic>=2.7.0`; zero provider SDKs are installed (`google-genai`, `openai`, `anthropic`).
- **Rationale for Deferral:**
  1. Creating a live GitHub Actions workflow or claiming live evaluation capability without an executable provider adapter or verified CI credentials would produce a hollow, non-functional workflow or broken CI runs.
  2. Committing a baseline claiming live model evaluation without executing actual live model calls would violate core project principles prohibiting fabricated metrics, benchmark claims, or synthetic run representations (D-014, D-021).
  3. The offline deterministic evaluation suite, fixture replay (`ReplayingLLMAdapter`), and baseline comparison CLI (`compare_cli.py`) already provide complete, verified 100% statement and branch coverage for all agent stages, coordinator lifecycle routing, failure modes, guardrail checks, rubric judging, and regression detection without external network dependencies, costs, or credential risks.
- **Consequences:** Live evaluation workflow creation, provider SDK installation, and live baseline establishment are formally deferred to a separately scoped milestone. Deterministic CI remains 100% credential-free and offline. No live baseline is committed; baseline comparison tools operate against reviewed offline replay baselines or future authorized live runs.
- **Revisit when:** A concrete provider adapter implementation (e.g. `AnthropicAdapter` or `GeminiAdapter`) is scoped, provider SDK dependencies are approved for addition to `pyproject.toml`, and validated provider credentials and quota are established for live evaluation.
