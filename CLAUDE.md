# CLAUDE.md

This file guides Claude Code (claude.ai/code) and other coding agents in this repository.

LLM agents from different model families play the social deduction game Imposter against
each other. The app is one Python package, `imposter`, built on Google's Agent Development
Kit (ADK), with a React web app in `frontend/` and Terraform in `infra/`. A pure game
engine owns the rules, and an ADK graph workflow of function nodes asks plain `LlmAgent`s
for their turns. The repository is also teaching material for ADK, so prefer what ADK
provides over code of our own.

## Commands

Dependencies are managed with `uv` for Python 3.13 and `npm` for the web app. Copy
`.env.example` to `.env` for local settings.

```
make sync           # uv sync --all-groups and npm ci in frontend/
make format         # ruff format and import sorting, Prettier
make lint           # ruff check --fix, the comment and docstring checkers, ESLint
make type           # ty check, tsc
make check          # format + lint + type + Terraform fmt/validate (no tests)
make test           # pytest with coverage (excluding `slow` tests), Vitest
make test-slow      # pytest -m slow (real model calls)
make play           # imposter play with real models (options in ARGS="...")
make dev            # the game API on port 8000 and the Vite dev server on port 5173
make frontend       # build frontend/dist, which the API app serves at /
make api-client     # regenerate frontend/src/api/schema.ts from the OpenAPI schema
make docker         # build the image and play it on port 8080 with .env and ADC
make adk-web        # the ADK developer UI, one game per session
make install-hooks  # install pre-commit hooks (including commit-msg)
```

`format`, `lint`, `type` and `test` each have a `-python` and a `-frontend` half, for
example `make test-frontend`. Run one test with
`uv run pytest tests/path/to/test_file.py::test_name` or
`cd frontend && npx vitest run src/path/to/file.test.ts`. There is no CI, so run
`make check test` before pushing.

## Where to find things

| Topic | Page |
|---|---|
| How the app is put together, the workflow, players, judge, design decisions, future work | [`docs/architecture.md`](docs/architecture.md) |
| The rules of the game, the options, events and views | [`docs/game-rules.md`](docs/game-rules.md) |
| The HTTP API, the event stream and the settings | [`docs/api.md`](docs/api.md) |
| The web app: stack, screens, playback | [`docs/frontend.md`](docs/frontend.md) |
| Traces, spans, attributes and content capture | [`docs/observability.md`](docs/observability.md) |
| What exists in GCP, why, and what it costs | [`docs/infrastructure.md`](docs/infrastructure.md) |
| Every style rule and what enforces it | [`docs/code-style.md`](docs/code-style.md) |
| Running, testing and common changes | [`docs/guides/development.md`](docs/guides/development.md) |
| The model catalog and adding a model | [`docs/guides/models.md`](docs/guides/models.md) |
| Setting up GCP and deploying | [`docs/guides/gcp-setup.md`](docs/guides/gcp-setup.md) |

## Hard rules

The tools enforce line length, annotations, docstring format, comment punctuation and
formatting. These rules are the ones that only review catches.

- Code is layered, and each layer imports only from the layers below it: `config` and
  `utils`, then `engine`, then `players`, then `orchestration`, then `agent` and `api`.
  `models` is used by `players` and above, and `telemetry`, `words` and `judge` by
  `orchestration` and above. The engine imports no ADK and calls no model.
- The engine decides every transition. A workflow node never decides what happens next,
  and a node either does I/O and only reads the game, or changes the game and does no
  I/O.
- A model is sent only what `game.view_for(seat)` allows. Never put session state,
  another seat's view or conversation history into a prompt.
- Behavior that reads or changes an object's state is a method on that object. Data
  types and enums carry no behavior. Plain functions are for logic on plain values.
- Pass arguments by keyword in calls to our own functions, methods and classes with two
  or more arguments.
- Separate distinct blocks of logic with a blank line: around every compound statement
  unless it starts or ends its block, and before the closing `return` of a function
  with three or more statements.
- Prefix names with their domain (`GameEvent`, not `Event`). Protocols end with
  `Protocol`, base classes start with `Base`, and subclasses of ADK types end with
  their kind (`Agent`, `Node`, `Classifier`, `Plugin`). Do not prefix names with `_`
  unless hiding clearly matters.
- Fill docstring prose and comments up to the 90-character limit by hand. In `src/`,
  document every argument and the return value.
- Exception messages are full sentences that end with a period. Pytest fixtures state
  their scope. Do not use `print`.
- Write prose in complete sentences with no em dashes and no semicolons, in US spelling.
  This covers docs, comments, docstrings, commit messages and pull request text.
- After changing an API model, an engine event or the `GameRequest`, run
  `make api-client` and commit the generated `schema.ts`.
- Commit messages follow conventional commits. Branches are named `feature/`, `fix/`
  or `chore/`. A pull request says how the change was verified.
- `uv.lock` is committed. Do not delete or gitignore it.

## Hooks

After every edit, `.claude/hooks/format-file.sh` formats the edited file and reports the
errors that remain on stderr. Fix them. When you stop, `make check` runs.

## Keep the documentation current

A change to behavior updates the page that describes it in the same pull request. When
you change a command, a setting, an event, a span, a node of the workflow or anything in
`infra/`, search `docs/` and `README.md` for its old name before you finish.
`docs/infrastructure.md` must match `infra/` and the manual GCP steps at all times.
