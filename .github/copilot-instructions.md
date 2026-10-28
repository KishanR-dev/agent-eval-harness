# Copilot Instructions — agent-eval-harness

`agent-eval-harness` is a Git-native evaluation and regression-testing harness for a two-stage LLM agent workflow (lead qualification -> outreach drafting).

## Documentation Pointers

Always read and follow the project specification documents:
- `SPEC.md` — Technical specification and architectural design (source of truth).
- `PLAN.md` — Step-by-step phased execution plan and evaluation strategy.
- `CHECKLIST.md` — Implementation checklist; items must be completed sequentially with evidence.
- `DECISIONS.md` — Dated record of architectural and scoping decisions (D-001 through D-016+).

## Engineering Conventions

- **Language & Runtime:** Python 3.11 managed via `uv`.
- **Contracts & Validation:** Pure Pydantic v2. Models use `ConfigDict(extra="forbid", strict=True)` without global whitespace stripping and without superficial top-level freezing. Versioning is explicit via SemVer (`"1.0.0"`) and typed with `Literal` to constrain exported JSON Schema.
- **Separation of Concerns:** Keep structural contract validation separate from business-policy rules.
- **Testing & Gates:** Deterministic tests must run 100% offline without provider keys or network access. Deterministic checks are the required gate in CI.
- **Attribution Hygiene:** Never introduce AI or tool co-author attribution in commit messages, trailers, or repository files (per D-011).
- **Metric Integrity:** Never invent, extrapolate, or estimate metrics. Report only measured results with real commands and output.

## Local PowerShell Commands (Windows)

All commands should be executed from the repository root in PowerShell:

```powershell
# 1. Environment creation (Python 3.11)
uv venv --python 3.11 .venv

# 2. Dependency installation (editable with dev dependencies)
uv pip install -e ".[dev]"

# 3. Formatting check & linting (Ruff)
uv run ruff format --check .
uv run ruff check .

# 4. Static type checking (Mypy)
uv run mypy src tests

# 5. Unit test suite with coverage (Pytest)
uv run pytest --cov=agent_eval_harness --cov-report=term-missing tests/
```
