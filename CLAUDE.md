# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project context

`docs/plans/README.md` is the main context for the project: vision, decisions, target repo
structure, work packages and the session workflow. Read it first in every session, then the
topic files and code the task points to.

## Project structure

One Python package `imposter` with a single `pyproject.toml` and `uv.lock` at the repo
root. Code is layered, and each layer imports only from the layers below it:
`config` and `utils` ← `engine` ← `players` ← `orchestration` ← `api`, with `models`
(used by `players` and above) and `words`, `judge` and `ports` used by `orchestration` and
`api`. `tests/test_layers.py` checks the layers that exist.

- `src/imposter/config.py` — the game options and the shared enums (`GameConfig`,
  `PlayerConfig`, `SecretWord`, `GamePhase`, ...), used across the package
- `src/imposter/utils/` — small functions on plain values, used across the package (word
  handling, vote tally, seat names, phase flow)
- `src/imposter/engine/` — pure game rules: the `Game` class (event log, queries,
  actions, player views), events and views (no ADK or LLM dependency)
- `src/imposter/players/` — `PlayerProtocol`, ADK player, fake players, prompt renderer
  and Jinja2 prompt templates (`prompts/*.md`)
- `src/imposter/models/` — model catalog (YAML) and ADK model factory
- `src/imposter/words/` — word categories, picker and generator
- `src/imposter/judge/` — `JudgeProtocol` port, LLM judge and cheap code checks
- `src/imposter/orchestration/` — `GameRunner` (asks players, applies turns), the game
  workflow (an ADK graph `Workflow` with a node per phase and a child node per turn) and
  the ADK `Runner` wiring
- `src/imposter/ports/` — game store and event bus protocols with in-memory adapters
- `src/imposter/telemetry/` — OpenTelemetry setup, span helpers, cost estimates
- `src/imposter/api/` — the API app: ADK's API server for the game app, plus the catalog
  route
- `src/imposter/web/` — static frontend (Alpine.js + Tailwind)
- `src/imposter/cli.py` — `imposter` command line entry point (Typer)
- `tests/` — mirrors `src/imposter/`, for example `tests/engine/` for `src/imposter/engine/`
- `scripts/tooling/` — development tooling such as the comment and docstring checkers
  (tests in `tests/tooling/`)
- `infra/` — Terraform (one flat root) for the app's resources in the existing sandbox
  project (no bootstrap; `make tf-setup` enables the base APIs and creates the state
  bucket)

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
make play           # imposter play with real models (options in ARGS="...")
make dev            # imposter serve --reload: the game API on port 8000
make adk-web        # adk web --otel_to_cloud src: the ADK developer UI, one game per session
make tf-setup       # once: base APIs and Terraform state bucket (gcloud)
make tf-plan        # terraform plan for infra (tf-apply to apply)
make install-hooks  # install pre-commit hooks (including commit-msg)
```

GCP setup in the sandbox project is described in `docs/setup.md`; what is created in
GCP, why and how it connects is in `docs/infrastructure.md`. Update that page in the same
PR as every change to `infra/` or to manual GCP steps. `uv run --env-file .env
python scripts/check_models.py` sends one test call per candidate model on Vertex AI.

Run a single test with:

```
uv run pytest tests/path/to/test_file.py::test_name
```

## Code style

See `docs/plans/tooling.md` for the full rules and how each one is enforced.

- No em-dashes (—) or semicolons in prose: docs, comments, docstrings, commit messages,
  PR and issue text. Split the sentence or use a comma or colon instead. Code syntax
  (for example a semicolon in a shell command) is fine.
- Write documentation in complete, flowing sentences, including list items and the
  explanation cells of tables. Avoid terse fragments such as "What the app creates, and
  why." or "Region: `europe-west4`."
- Top-level documentation (`README.md` and `docs/*.md`, not `docs/plans/`) stands on its
  own and describes the system, not how it was built. Do not refer to work packages,
  issues, PRs or plan decisions (`D17`). Mark parts that do not exist yet as planned.
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
- Exception messages are full sentences: they start with a capital letter and end with a
  period, for example `"Seat 2 has no turn to start in phase vote."`.
- Do not split lines manually or add trailing commas to force splits; let `ruff format`
  wrap (`skip-magic-trailing-comma = true`).
- Pytest fixtures always state their scope explicitly, for example `scope="function"`.
- Keep it simple, and use objects where state or shared logic lives. Behaviour that reads
  or changes an object's state is a method on that object, for example
  `game.submit_clue(...)`, `game.view_for(seat)` and `runner.play(game)`. Objects change in
  place: no copy-and-reassign updates. Plain functions only for logic on plain values
  without an owning object (`utils/text.py`, `utils/tally.py`, `utils/phases.py`).
  Data types (pydantic models for configs, events, views and responses) and enums carry
  data and validation only, no behaviour methods. Keep I/O at the edges: the step that
  calls a model returns data, and a separate step applies it to the game.
- Use specific, descriptive names, consistent across the package. Prefix types, enums and
  constants with their domain (`GameEvent`, `PlayerView`, `JudgeVerdict`) instead of a
  bare generic word (`Event`, `View`, `Verdict`). Related types share a pattern, for
  example the per-phase responses `ClueResponse`, `DiscussionResponse`, `VoteResponse`.
- Name abstract types by their kind: base classes start with `Base` (`BaseGameEvent`),
  protocols end with `Protocol` (`PlayerProtocol`), ADK agents end with `Agent`
  (`StructuredTaskAgent`) and workflow nodes with `Node` (`GamePhaseNode`). Functions
  are named after what they return or do (`pending_seats`, `start_turn`), not `get_` or
  `do_`.
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
