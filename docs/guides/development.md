# Developing locally

This guide gets the app running on a laptop and lists the commands, tests and checks you
use while changing it. It assumes a GCP project in which the models answer, which
[`gcp-setup.md`](gcp-setup.md) sets up. Games with fake players and all tests except the
slow ones need no GCP at all.

## Prerequisites

| Tool | Version | Where the version comes from |
|---|---|---|
| Python | 3.13 | `requires-python` in `pyproject.toml` |
| `uv` | recent | It installs Python packages from `uv.lock`. |
| Node.js | 24 | `frontend/.nvmrc` |
| `gcloud` | recent | It provides the credentials for Vertex AI. |
| Terraform | optional | `make check` formats and validates `infra/` when it is installed. |

## Setup

1. Install the dependencies of the package and the web app.

   ```
   make sync
   ```

2. Copy the settings and set the project.

   ```
   cp .env.example .env
   ```

   Set `GOOGLE_CLOUD_PROJECT` in `.env` to the ID of your project.

3. Create the credentials the Google clients use.

   ```
   gcloud auth application-default login
   ```

4. Install the pre-commit hooks, which check the commit message and run `make check`.

   ```
   make install-hooks
   ```

5. Play a game in the terminal.

   ```
   make play
   ```

## Commands

| Command | What it does |
|---|---|
| `make sync` | It runs `uv sync --all-groups` and `npm ci` in `frontend/`. |
| `make format` | It formats Python with ruff and the web app with Prettier. |
| `make lint` | It runs `ruff check --fix`, the comment and docstring checkers and ESLint. |
| `make type` | It runs `ty check` and `tsc`. |
| `make check` | It runs format, lint, type and the Terraform format and validation. It runs no tests. |
| `make test` | It runs pytest with coverage, without the `slow` tests, and Vitest. |
| `make test-slow` | It runs `pytest -m slow`, which calls real models and loads `.env`. |
| `make play` | It plays a game with real models. Options go in `ARGS="..."`. |
| `make dev` | It serves the API on port 8000 and the Vite dev server on port 5173. |
| `make frontend` | It builds `frontend/dist`, which the API app serves at `/`. |
| `make api-client` | It regenerates `frontend/src/api/schema.ts` from the OpenAPI schema. |
| `make docker` | It builds the image and runs it on port 8080 with `.env` and your credentials. |
| `make adk-web` | It starts ADK's developer UI, in which every new session plays a game. |
| `make install-hooks` | It installs the pre-commit hooks. |

`format`, `lint`, `type` and `test` each have a `-python` and a `-frontend` half, for
example `make test-frontend`. The frontend halves install `frontend/node_modules` from
the lockfile when it is missing or stale. The deploy commands are in
[`gcp-setup.md`](gcp-setup.md).

## Settings

`.env` holds the local settings, and the Makefile reads it too.

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | none | The project that model calls and traces are billed to. |
| `GOOGLE_CLOUD_LOCATION` | `global` | The Vertex AI location of Gemini calls. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE` | It makes the Google clients use Vertex AI. |
| `IMPOSTER_TELEMETRY` | `cloud` with a project, otherwise `none` | Where traces go: `cloud`, `console` or `none`. |
| `IMPOSTER_DEV_USER` | empty | The user recorded on traces in place of the IAP identity. |
| `GEMINI_API_KEY` | empty | With it, the judge uses the Gemini Decisions API. Without it, the judge asks Gemini Flash-Lite on Vertex AI. |

## Tests

| Suite | Where | What it covers |
|---|---|---|
| Engine | `tests/engine/` | The rules, and Hypothesis property tests that no view or prompt leaks the word, another seat's reasoning or a hidden vote. |
| Workflow | `tests/orchestration/` | Whole games through the ADK workflow with fake players, retries, fallbacks, the budget, golden event logs of seeded games, and what real agents are sent. |
| Players | `tests/players/` | `LlmPlayer` on a fake model: streaming, schema retries, errors, and snapshots of every prompt. |
| Judge | `tests/judge/` | The code checks, the judge on a fake model and the Decisions adapter against a stand-in API. |
| API | `tests/api/` | The routes and a game streamed over `/run_sse` with fake players. |
| Web app | `frontend/src/**/*.test.ts` | The stream client and the logic in `lib/`. |
| Slow | `*_slow.py` | Real models on Vertex AI, and the real Decisions API when its key is set. |

Run one test with one of these.

```
uv run pytest tests/path/to/test_file.py::test_name
cd frontend && npx vitest run src/path/to/file.test.ts
```

`UPDATE_SNAPSHOTS=1 uv run pytest tests/players/test_prompt.py` rewrites the prompt
snapshots after a deliberate change to a template. The golden event logs in
`tests/orchestration/snapshots/` pin the behavior of the workflow, and no script
regenerates them.

There is no CI. Run `make check test` before you push.

## Common tasks

**Change a prompt.**

1. Edit the template in `src/imposter/players/prompts/`.
2. Run `UPDATE_SNAPSHOTS=1 uv run pytest tests/players/test_prompt.py` and read the diff
   of the snapshots.
3. Run `make test-python`, which includes the leak tests on rendered prompts.

**Change an engine event, an API model or the `GameRequest`.**

1. Make the change in `src/imposter/`.
2. Run `make api-client` and commit the generated `frontend/src/api/schema.ts`.
3. Run `make check test`.

**Add a node or change the flow.**

1. Change `GameWorkflowBuilder` in `src/imposter/orchestration/workflow.py`. Keep I/O in
   nodes that only read the game, and changes to the game in nodes that do no I/O.
2. Update the graph test in `tests/orchestration/test_workflow.py`.
3. Update [`../architecture.md`](../architecture.md) and, when spans change,
   [`../observability.md`](../observability.md).

**Add or change a model.** Follow [`models.md`](models.md).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `DefaultCredentialsError` | There are no application default credentials. Run `gcloud auth application-default login`. |
| `player failed: ... 429` in a game | The quota of that model is too low. See the quota step in [`gcp-setup.md`](gcp-setup.md). |
| `player failed: ... 404` or `Publisher model ... not found` | The model is not enabled in Model Garden or not served in that location. Run `scripts/check_models.py`. |
| The web app shows a 403 on `make dev` behind another proxy | ADK refuses browser requests from another origin. Add the origin to `IMPOSTER_ALLOW_ORIGINS`. |
| `make check` changes files | The formatters fixed something. Stage the changes and commit again. |
| A commit is refused by `commit-msg` | The message is not a conventional commit, such as `feat(engine): add a phase`. |
| `tsc` fails after an API change | `frontend/src/api/schema.ts` is stale. Run `make api-client`. |
