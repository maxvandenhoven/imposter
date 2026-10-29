# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project context

`docs/plans/README.md` is the main context for the project: vision, decisions, target repo
structure, work packages and the session workflow. Read it first in every session, then the
topic files and code the task points to.

## Project structure

One Python package `imposter` with a single `pyproject.toml` and `uv.lock` at the repo
root. The dependency direction is `engine ← players ← orchestration ← api`, with `models`,
`words`, `judge` and `ports` used by `orchestration` and `api`.

- `src/imposter/engine/` — pure game state machine, rules, views and tally (imports
  nothing from the rest of the package, no ADK or LLM dependency)
- `src/imposter/players/` — `Player` protocol, ADK player, fake players, prompts
- `src/imposter/models/` — model catalog (YAML) and ADK model factory
- `src/imposter/words/` — word categories, picker and generator
- `src/imposter/judge/` — `Judge` port, LLM judge and cheap code checks
- `src/imposter/orchestration/` — `GameMaster` agent and ADK runner wiring
- `src/imposter/ports/` — game store and event bus protocols with in-memory adapters
- `src/imposter/telemetry/` — OpenTelemetry setup, span helpers, cost estimates
- `src/imposter/api/` — FastAPI app, settings, identity, routes (games, catalog, SSE)
- `src/imposter/web/` — static frontend (Alpine.js + Tailwind)
- `src/imposter/cli.py` — `imposter` command line entry point (Typer)
- `tests/` — mirrors `src/imposter/`, for example `tests/engine/` for `src/imposter/engine/`
- `scripts/tooling/` — development tooling such as the comment and docstring checkers
  (tests in `tests/tooling/`)
- `infra/` — Terraform (one flat root) for the app's resources in the existing sandbox
  project (no bootstrap; `make tf-state-bucket` creates the state bucket)

## Setup and commands

Dependency management uses `uv`. Python 3.13.x is required (no other minor versions).
Copy `.env.example` to `.env` for local settings.

```
make sync           # uv sync --all-groups
make format         # ruff format and import sorting
make lint           # ruff check --fix, the comment and docstring checkers
make type           # ty check
make check          # format + lint + type + Terraform fmt/validate (no tests)
make test           # pytest with coverage, excluding `slow` tests
make test-slow      # pytest -m slow (real Vertex AI calls)
make tf-state-bucket # create the Terraform state bucket once (gcloud)
make tf-plan        # terraform plan for infra (tf-apply to apply)
make install-hooks  # install pre-commit hooks (including commit-msg)
```

GCP setup in the sandbox project is described in `docs/setup.md`. `uv run python
scripts/check_models.py` sends one test call per candidate model on Vertex AI.

Run a single test with:

```
uv run pytest tests/path/to/test_file.py::test_name
```

## Code style

See `docs/plans/tooling.md` for the full rules and how each one is enforced.

- Line length: 90 characters for code, docstrings and comments.
- Type annotations on every function and method, including private ones and tests (ruff
  `ANN`, no test exemptions). Test functions return `-> None`.
- Google-style docstrings on public classes and functions (ruff `D`, `convention =
  "google"`). Do not repeat types in `Args:` or `Returns:`; the annotations carry them.
- In `src/`, every docstring documents all arguments in `Args:` and the return value in
  `Returns:` (`Yields:` for generators) unless the annotation is `None`. Checked by
  `scripts/tooling/check_docstrings.py` (part of `make lint`). FastAPI routes and typer
  commands set their public text with `description=` and `help=`.
- Use single backticks (`` `code` ``) for inline code in docstrings, not double backticks.
- Fill docstring prose and comments up to the 90-character limit by hand; do not wrap
  earlier. No tool reflows them, and ruff `E501` flags lines past 90 characters.
- Comments start with a capital letter and end with a period, unless shorter than 5 words.
  Checked by `scripts/tooling/check_comments.py` (part of `make lint`).
- No `print` statements (ruff `T20`); use `logging` instead.
- Do not split lines manually or add trailing commas to force splits; let `ruff format`
  wrap (`skip-magic-trailing-comma = true`).
- Pytest fixtures always state their scope explicitly, for example `scope="function"`.
- Behaviour is a method on the type that owns the data it reads. Plain functions only for
  math on primitives without an owning type (for example `engine/tally.py`).
- Use specific, descriptive names, consistent across the package. Prefix types, enums and
  constants with their domain (`GameEvent`, `PlayerView`, `JudgeVerdict`) instead of a
  bare generic word (`Event`, `View`, `Verdict`). Related types share a pattern, for
  example the per-phase responses `ClueResponse`, `DiscussionResponse`, `VoteResponse`.
- Prefer public over private. Do not prefix functions, methods, attributes or constants
  with `_` unless hiding them clearly matters (state that must only change through
  methods, or a subclass hook that callers must not use). Document public attributes in
  the class `Attributes:` section. This applies to tests as well.
- Separate distinct blocks of logic with a blank line: before and after every compound
  statement (`if`, `for`, `while`, `with`, `try`, `match`) unless it starts or ends its
  enclosing block, and before the closing `return` of a function with several steps
  (three or more statements, not counting the docstring).
- Pass arguments by keyword in calls to our own functions, methods and classes with two
  or more arguments, for example `engine.submit_vote(voter=seat, target=suspect)`.
  Positional is fine for single-argument calls, the standard library, builtins,
  third-party APIs (`isinstance`, logging format arguments, `pytest.mark.parametrize`) and
  `*args` parameters. Apply it consistently.
- `uv.lock` is committed; do not delete or gitignore it.

## Type checking

Uses `ty` (Astral) — not mypy. Run via `make type`.

## Claude Code hooks

- PostToolUse on `Edit|Write|MultiEdit` runs `.claude/hooks/format-file.sh`, which formats
  the edited `.py` file with `ruff format` and `ruff check --fix`, then runs the comment
  checker (and the docstring checker for files in `src/`). Remaining errors are reported
  back on stderr; fix them.
- Stop runs `make check`.

## Git workflow

- Branch naming: `feature/`, `fix/`, `chore/` prefixes.
- Commit messages follow conventional commits (enforced by the commitizen pre-commit hook).
- The pre-commit hook also runs `make check`. Install hooks once with `make install-hooks`.
- There is no CI; run `make check test` before pushing.
- PRs reference their issue with `Closes #N` and include a *Verification* section.
