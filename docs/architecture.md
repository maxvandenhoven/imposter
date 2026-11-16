# Architecture

This page explains how the app is put together and why. Read it before a change that
crosses folders. The reference pages hold the exact values: [`game-rules.md`](game-rules.md)
for the game, [`api.md`](api.md) for the HTTP API and the event stream,
[`frontend.md`](frontend.md) for the web app, [`observability.md`](observability.md) for
traces and [`infrastructure.md`](infrastructure.md) for what runs in GCP.

## Overview

LLM agents from different model families play the social deduction game
[Imposter](https://imposter.app/) against each other. Every civilian knows a secret word,
the imposter does not, and the players give clues, discuss, vote and guess. The app is a
demo for three things: agents built with Google's Agent Development Kit (ADK), deployment
on GCP and tracing.

The main constraint is that the game must be fair and repeatable while the players are
language models. So the rules are deterministic code, no model decides what happens
next, and each model is told only what its seat may know. A second constraint is that
the app should be a clear example of ADK, so it uses ADK's own building blocks and adds
as little as possible around them.

| Layer | Choice |
|---|---|
| Language and packaging | Python 3.13, one package `imposter`, `uv` with a committed lockfile |
| Agents | Google ADK 2.x: a graph `Workflow` of function nodes, `LlmAgent`, session state, classifiers |
| Models | Vertex AI: Gemini natively, Claude and open models through ADK's `LiteLlm` |
| Judge | The Gemini Decisions API with an API key, or Gemini Flash-Lite on Vertex AI |
| API | ADK's API server (FastAPI) with two extra routes, events over SSE |
| Web app | React, Vite, TypeScript, Tailwind CSS, shadcn/ui |
| Tracing | OpenTelemetry to Cloud Trace and Cloud Logging |
| Hosting | One container on Cloud Run behind IAP, managed with Terraform |

## Repository layout

```
imposter/
├─ pyproject.toml, uv.lock     # the package, its dependencies and the tool settings
├─ Makefile                    # every developer and deploy command
├─ Dockerfile                  # Node stage builds the web app, uv stage installs, uvicorn serves
├─ cloudbuild.yaml             # builds the image in Cloud Build
├─ CLAUDE.md                   # entry point for coding agents
├─ .claude/                    # agent hooks: format after an edit, check on stop
├─ .env.example                # local settings, copied to .env
├─ docs/                       # this documentation
├─ src/imposter/
│  ├─ config.py                # GameConfig, PlayerConfig, SecretWord and the shared enums
│  ├─ utils/                   # functions on plain values: names, phases, tally, text
│  ├─ engine/                  # the pure rules: Game, events, views, responses
│  ├─ models/                  # the model catalog (YAML) and the ADK model factory
│  ├─ players/                 # PlayerProtocol, LlmPlayer, the prompt renderer and templates
│  ├─ words/                   # word categories, picker, generator and word options
│  ├─ judge/                   # Judge, the Gemini Decisions adapter, the code checks
│  ├─ orchestration/           # the game workflow, the ADK app and runner, the request
│  ├─ telemetry/               # exporter setup, span helpers, cost estimate
│  ├─ api/                     # ADK's API server plus the catalog and trace routes
│  ├─ agent.py                 # the ADK app that the API and adk web load
│  └─ cli.py                   # the imposter command: play, serve, openapi, version
├─ frontend/                   # the React web app, built into frontend/dist
├─ tests/                      # mirrors src/imposter, plus fakes.py and tooling tests
├─ scripts/                    # check_models.py, measure_models.py, tooling/ checkers
└─ infra/                      # one flat Terraform root for the app's GCP resources
```

Code is layered, and each layer imports only from the layers below it. `config` and
`utils` are at the bottom, then `engine`, then `players`, then `orchestration`, then
`agent` and `api`. `models` is used by `players` and above, and `telemetry`, `words` and
`judge` are used by `orchestration` and above. `config`, `utils` and `engine` use only
the standard library and pydantic. `tests/test_layers.py` checks both rules.

## How a game flows

1. A client puts a `GameRequest` (the options and how to choose the word) in the state
   of a new ADK session, under `game:request`. The web app does that with
   `POST /apps/imposter/users/{user_id}/sessions`, and the CLI does it in process
   (`orchestration/play.py`). The session id is the game id.
2. The client runs the session. ADK's `Runner` starts the game workflow
   (`orchestration/workflow.py`).
3. The `setup` node resolves the secret word (`words/options.py`), creates the game with
   `Game.create` and saves its snapshot in the session state under `game`.
4. The `next_turns` node asks the engine which seats act next and starts their turns.
5. The `play_turn` node runs once per started seat. It asks the seat's player
   (`players/llm_player.py`), which runs one `LlmAgent` on the seat's model, and it
   checks the answer against the rules and the judge (`judge/judge.py`).
6. The `apply_turns` node applies the answers to the game with `game.submit` and saves
   the snapshot. The engine moves on to the next seat, round or phase by itself.
7. Steps 4 to 6 repeat until the engine says the game is over. The `finish` node then
   ends the run.
8. Every node that changes the game yields one ADK event per new engine event. The
   client reads the engine event from `custom_metadata["game_event"]` and shows it.

## Domain model

| Entity | Where | What it is |
|---|---|---|
| `GameRequest` | `orchestration/setup.py` | The `GameConfig` plus `WordOptions`: everything a client sends to start a game. |
| `GameConfig` | `config.py` | The options of a game: 3 to 8 `PlayerConfig`s, the number of imposters, rounds, caps, the token budget and a seed. |
| `SecretWord` | `config.py` | The word, its category and the imposter hint, fixed before the game is created. |
| `Game` | `engine/game.py` | The setup and an append-only event log. Every query is derived from the log. |
| `GameEvent` | `engine/events.py` | One state change, with a `seq`, a phase, a visibility and private fields. |
| `PlayerView` | `engine/views.py` | Everything one seat may see at one moment, built by `game.view_for(seat)`. |
| Phase responses | `engine/responses.py` | The structured answer of each phase, such as `ClueResponse`. |
| `GameSnapshot` | `engine/game.py` | A game as data, for the session state. `Game.load` rebuilds the game. |
| `TurnResult` | `orchestration/workflow.py` | What one turn produced: the response, a rejection, a verdict, token usage and errors. |
| `ModelCatalogEntry` | `models/catalog.py` | One model that can play a seat, with its ADK model string and settings. |

The engine enforces the rules of [`game-rules.md`](game-rules.md). The ones that matter
across folders are these.

- The current phase is the phase of the last event, so nothing but the engine can move a
  game forward.
- A seat acts only after `game.start_turn(seat)`. Acting out of turn raises
  `InvalidActionError`.
- A missing or rejected answer becomes the fallback of the phase in `game.submit`, so a
  failing model never stops a game.
- A view never contains the secret word for an imposter, another seat's private
  reasoning, or a vote before the votes are revealed. Property tests check this
  (`tests/engine/test_leaks.py`).

## Entry points

| Entry point | File | What it does |
|---|---|---|
| `imposter play` (`make play`) | `cli.py` | It plays one game in the terminal and prints the events, the cost and the trace link. |
| `imposter serve` (`make dev`) | `cli.py`, `api/app.py` | It serves the API and, when it is built, the web app. |
| `imposter openapi` (`make api-client`) | `cli.py`, `api/openapi.py` | It writes the OpenAPI schema that the frontend types are generated from. |
| `adk web src` (`make adk-web`) | `agent.py` | It opens ADK's developer UI, where every new session plays a default game. |
| `uvicorn --factory imposter.api.app:create_app` | `api/app.py` | It is what the container runs. |
| `scripts/check_models.py` | `scripts/` | It sends one test call per candidate model on Vertex AI. |
| `scripts/measure_models.py` | `scripts/` | It times one realistic turn per catalog model. |

There is no `imposter tournament` command yet, see [Future work](#future-work).

## Game workflow

`GameWorkflowBuilder` in `orchestration/workflow.py` holds what the nodes need (the word
resolver, the player seating, the judge and an optional default request) and builds an
ADK `Workflow`. Each node is a method of the builder, wrapped with ADK's `node(...)`.

```
START → setup → next_turns ──turn──→ play_turn → apply_turns ─┐
                   ▲   └──over──→ finish                       │
                   └───────────────────────────────────────────┘
```

| Node | ADK feature | Responsibility |
|---|---|---|
| `setup` | Function node that runs child nodes | It reads the request, chooses the word, creates the game and saves it. A session that already has a game keeps it. |
| `next_turns` | Function node with a route | It starts one turn in a sequential phase and every pending turn in a parallel phase, and outputs the seats. It routes to `finish` when the game is over. |
| `play_turn` | Function node as a `parallel_worker` | ADK runs it once per seat, at the same time. It asks the player, checks the answer and asks once more with the reason when the answer is rejected. It only reads the game. |
| `apply_turns` | Function node | It gets the results in seat order, records usage and errors, and submits each answer or its fallback. |
| `finish` | Function node | It ends the run with a line on how the game ended. |

The constraints that shaped it are these.

- **The engine decides.** No node chooses a transition. Phases without players, the
  resolution and the outcome, are played by the engine when the phase before them ends,
  so one loop plays every phase and every config.
- **The game lives in session state.** A node loads the game from `ctx.state["game"]`,
  and a node that changes it saves it back. Nothing lives outside ADK between nodes, so
  there is no registry of running games and nothing to clean up. A session whose run
  stopped early plays on when it is run again.
- **Asking and applying are separate nodes.** `play_turn` does the I/O and returns data.
  `apply_turns` changes the game. The turns of a parallel phase therefore run against
  the same game, and because ADK returns their results in input order, the event log
  does not depend on which model answered first.
- **Models never see state.** The state holds the secret word and every private
  reasoning. An agent gets none of it, see [Players](#players).

## Players

A player implements `PlayerProtocol` (`players/base.py`): one method, `take_turn`, which
gets the ADK context of the turn, the `PlayerView` of the seat, a callback for token
usage and the reason a previous attempt was rejected, and returns the response of the
phase or raises. `PlayerSeatingProtocol` decides who plays a seat.

| File | Responsibility |
|---|---|
| `players/llm_player.py` | `LlmPlayer` builds one plain `LlmAgent` per turn and runs it as a child node. `LlmPlayerSeating` seats a player with the model of each seat's config. |
| `players/prompt.py` | `PlayerPromptRenderer` renders the instruction and the task from a view with the Jinja2 templates in `players/prompts/`. |
| `models/factory.py` | `adk_model` builds the ADK model object of a catalog entry, with its timeout and retries, and `generate_content_config` the settings of a phase. |
| `tests/fakes.py` | `ScriptedPlayer` and `RandomPlayer` implement the same protocol without a model, for tests. |

The agent of a turn is configured so that ADK does the work.

- `output_schema` is the response type of the phase, so ADK validates the answer.
- `retry_config` lets ADK run the agent again, up to three model calls, when the answer
  misses the schema or the stream breaks off midway.
- `include_contents='none'` sends no conversation history. All the agent knows is its
  instruction, which is rendered from the view of its seat, and the task of the phase.
- The instruction is a function, not a string, so ADK fills no `{key}` placeholders from
  session state.
- It runs with `ctx.run_node` inside the game run, so its tokens stream to the client
  and its spans sit below the turn.
- A `before_model_callback` removes the response schema for models without native
  structured output, which are asked for JSON in the task instead.
- An `after_model_callback` reports the tokens of every call, also of calls whose answer
  is rejected afterwards, and raises when the model answers with an error.

Two findings about the models shaped this. Claude Sonnet refuses the game instruction as
a system prompt, so a short fixed `static_instruction` is the system instruction and ADK
sends the rendered instruction as user content. Open models on Vertex AI often stall for
tens of seconds, so calls through LiteLLM have a 10 second limit and are retried, while
Gemini calls have 60 seconds. [`guides/models.md`](guides/models.md) has the details.

## Judge

The judge decides what code cannot: whether a guess that is not an exact match names the
secret word, and whether a clue is a trivial derivative of it.

| File | Responsibility |
|---|---|
| `judge/checks.py` | The cheap code checks, which run first: exact match after normalization, one word inside the other, a shared stem. |
| `judge/judge.py` | `Judge` asks one yes or no question through an ADK classifier and turns the probability into a `JudgeVerdict`. |
| `judge/decisions.py` | `GeminiDecisionsClassifier` puts the Gemini Decisions API behind ADK's classifier interface. |

ADK's classifier interface (`google.adk.labs.classifiers`, experimental) takes an input
and typed questions and returns probabilities instead of text. The judge sends the facts
as JSON and one `Binary` question, and the verdict is whether the probability of a yes
reaches the threshold of 0.5. For a clue, the question is whether it is a trivial
derivative, so a yes makes the clue invalid. When the classifier fails or declines to
answer, the judge gives the lenient verdict: the clue is valid and the guess is not the
word.

`Judge.load()` picks the classifier. With `GEMINI_API_KEY` set, it is the Gemini
Decisions API (`gemini-decision-1`), a model that answers such questions with a
calibrated probability in one fast call. Without the key it is ADK's `LlmClassifier` on
Gemini Flash-Lite on Vertex AI at temperature 0. The Decisions API is part of the Gemini
Developer API and not of Vertex AI, which is why it needs an API key. The adapter calls
the REST endpoint with `httpx`, because the SDK support is in `google-genai` 3.2 and
later, and ADK 2.14 requires an older `google-genai`. Its wire format was taken from the
SDK source and is covered by tests against a stand-in. It has not been run against the
real API yet: `tests/judge/test_decisions_slow.py` does that when the key is set.

## Words

| File | Responsibility |
|---|---|
| `words/categories/*.yaml` | The built-in categories, 30 to 50 words each. Most are abstract (emotions, concepts, sensations, sounds), so one clue does not give the word away. |
| `words/picker.py` | `WordPicker` picks a random word and remembers recently used ones. |
| `words/generator.py` | `WordGenerator` holds two plain `LlmAgent`s on Gemini Flash-Lite: one makes up a word with a category and a hint, one gives the hint for a known word. |
| `words/options.py` | `WordOptions` are the choices of the setup screen, and `SecretWordResolver` turns them into a `SecretWord`. A hint that mentions the word is rejected. |

The `setup` node runs the generator's agents as child nodes, so their model calls are
part of the game run and its trace.

## Cross-cutting concerns

- **API.** The backend is ADK's API server. A game is a session and playing it is a
  run, so there are no game routes of the app's own. [`api.md`](api.md) has the routes
  and the stream.
- **Tracing.** ADK traces the workflow, every node, every agent and every model call.
  A plugin puts the game attributes on the root span, and the app adds spans for judge
  decisions and Decisions API calls. [`observability.md`](observability.md) has the
  hierarchy and the attributes.
- **Cost.** Each model call has a `max_output_tokens` per phase, and a game is aborted
  when it passes its token budget (200,000 by default). The engine's `usage` events
  drive the cost estimate of the CLI and the web app.
- **Deployment.** One image serves the API and the built web app on Cloud Run, behind
  IAP, scaling to zero. [`infrastructure.md`](infrastructure.md) has every resource.
- **Tests.** [`guides/development.md`](guides/development.md) lists the test suites.
  There is no CI: the checks run locally and in a pre-commit hook.

## Design decisions

- **Deterministic orchestration, no LLM game master.** A graph of code nodes drives a
  pure engine. Rules cannot be broken, information hiding holds by construction, and
  each turn is a clean span.
- **Only ADK primitives.** The workflow is function nodes, a parallel worker, session
  state, plain `LlmAgent`s and `RetryConfig`. An earlier version had a custom node class
  per phase, live game objects in a registry, an event bus and a player class that
  wrapped five agents with its own retry loop. The loop of function nodes plays the same
  seeded games event for event (`tests/orchestration/snapshots/`) with about half the
  orchestration and player code.
- **One turn loop instead of a node per phase.** The loop is simpler and plays every
  config. The price is that `adk web` draws the loop and not the phases, and that the
  phase is an attribute of each turn span and not a span of its own.
- **The game in session state.** State is the place ADK gives a workflow for data
  between nodes, and it makes the session the complete record of a game. The price is
  size: each save puts the whole event log in an event's state delta, about 0.4 MB over
  a game of four players and 1.2 MB over a game of eight.
- **Schema retries without the error text.** ADK's `RetryConfig` runs the agent again
  with the same request, so the model does not see why its JSON was rejected. That is
  ADK's way, and it removed a retry loop. The retry after a rule violation does carry
  the reason, because that is game logic in `play_turn`.
- **A small player protocol.** The workflow asks a `PlayerProtocol` instead of building
  agents itself. That keeps tests fast, because fake players need no model, and leaves
  room for players that are not local agents.
- **All models on Vertex AI, with one exception.** One bill, one set of quotas and no
  API keys for the players. The judge's Decisions API is the exception, because it has
  no Vertex AI endpoint, and the judge works without it.
- **A decision model as judge.** A judge answers yes or no. A model that returns a
  calibrated probability fits that better than generated text, and ADK's classifier
  interface makes the backend a setting.
- **ADK's API server instead of an API of the app's own.** ADK already streams runs
  over SSE and cancels a run when its client leaves. The price is that a client cannot
  reconnect to a running game.
- **A game runs inside its request.** Cloud Run bills CPU only during requests, so the
  game runs for as long as `POST /run_sse` is open. One instance plays one game at a
  time.
- **Everything in memory.** Sessions live in ADK's `InMemorySessionService`. Scaling to
  zero loses them, which is fine for a demo.
- **Saying the secret word loses at once.** In a real game an imposter inferred the word
  from the first clue and gave it as its own clue. The rule of that time turned such a
  clue into a pass and the game went on, so the rule became that whoever says the word
  loses for their side.
- **Hidden, abstract categories.** In the same game a concrete public category made the
  word guessable from one clue. Categories are now hidden by default and mostly
  abstract.
- **Private reasoning with every answer, and a debrief.** Each response has a
  `private_reasoning` field, and after the reveal every player reflects on its play.
  The web app shows both side by side, to compare reasoning in the moment with
  reasoning after the fact.

## Future work

- **Tournament CLI.** An `imposter tournament` command that plays many games and
  reports win rates, detection accuracy and guess accuracy per model.
- **Persistence.** A database or Vertex AI session service, which would persist games
  without a change to the workflow, and a list of past games in the web app.
- **Personas.** `PlayerConfig.persona` and the empty `persona.md` template are reserved
  for a play style per seat.
- **Remote players.** A player that calls a remote agent over the A2A protocol, behind
  `PlayerProtocol`.
- **ADK's Gemini Decisions classifier.** When ADK ships its own adapter, or allows
  `google-genai` 3, `judge/decisions.py` can go.
- **More judges.** Any ADK `BaseClassifier` works, for example a self-hosted decision
  model, and the judges can be compared on the same games.
- **Clue leakiness.** One Decisions API request per finished game could score every clue
  on how much it gives away, for tournament statistics.
- **Team display.** The engine supports several imposters, and the web app does not show
  teams yet.
- **ADK's eval framework.** Eval sets per phase, such as "a civilian clue does not
  reveal the word".
- **CI/CD.** A pipeline that runs the checks and deploys on merge.
