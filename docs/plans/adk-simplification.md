# ADK simplification plan

This plan replaced the custom orchestration code with ADK primitives: function nodes, a
parallel worker, plain `LlmAgent`s, session state, node retries and ADK's classifier
interface for the judge. The game rules stay in the pure `Game` engine and the graph stays
deterministic. The plan is implemented. The sections below are the plan as it was
written, and this summary records how it ended.

- The decisions of §6 were taken as recommended, except C: the judge uses the Gemini
  Decisions API with an API key as soon as `GEMINI_API_KEY` is set, as an exception to
  D5, and falls back to `LlmClassifier` on Vertex AI without the key.
- The workflow got a fifth node, `finish`, because ADK warns when a routed node emits no
  route. A session whose run stopped early plays on when it is run again.
- The player port stayed a small protocol (`PlayerProtocol.take_turn`) instead of "any
  node", because the fake players of the tests need the view and the retry reason.
- The size estimate of §2 was too optimistic. Without docstrings and comments, the
  orchestration code went from 529 to 277 lines and the player code from 415 to 209
  (170 of those were the fake players, which moved to `tests/`). The ports (67) and
  `StructuredTaskAgent` (49) are gone. The engine grew by 131 lines, because the
  response models and the dispatch moved into it, and the judge grew from 134 to 289,
  because the Decisions adapter is new. The whole package went from 3,143 to 2,864
  lines of code.
- ADK was upgraded to 2.14.1, which the classifier types need.

## 1. Goals and constraints

- The workflow uses the patterns of the ADK docs: a `Workflow` of function nodes with
  routes and a loop edge, a `parallel_worker` for fan-out, dynamic child nodes with
  `ctx.run_node`, `RetryConfig` and `timeout` on nodes, and data in `ctx.state`.
- A player is a plain `LlmAgent` with `output_schema`, so streaming, tracing and
  validation come from ADK without wrapper code.
- The game rules stay deterministic and outside the models (D6). The engine still
  decides every transition, every view and every fallback.
- Every existing feature keeps working: the React board with streamed answers, the CLI,
  `adk web`, the trace per game, the token budget, retries and fallbacks, the judge, the
  word generator and the leak tests.
- The frontend contract stays the same: events of author `game_runner` carry the engine
  event in `customMetadata.game_event`, and partial events of author
  `player_{seat}_{phase}` carry the streamed answer.

## 2. What is custom today

| Code | Lines | Why it exists | ADK primitive that replaces it |
|---|---|---|---|
| `orchestration/runner_workflow.py` | 457 | It holds two `Node` subclasses, a registry of live games by session id (`GameSessions`, `GameSession`) and a publish cursor for the bus. | Function nodes replace the subclasses, and `ctx.state` replaces the registry. |
| `orchestration/runner.py` | 387 | `GameRunner` asks players, retries, checks rules and applies answers through a large `match` on phase and response type. | A `parallel_worker` node asks, a function node applies, and the dispatch moves onto `Game`. |
| `players/adk_player.py` | 322 | `AdkPlayer` wraps five agents per seat, keeps the current view and usage on the instance and runs its own retry loop over error codes. | One plain `LlmAgent` per turn, an instruction provider that reads state, and `RetryConfig` on the node. |
| `players/base.py` | 146 | `PlayerProtocol`, `PlayerResponse` and `TurnUsage` wrap the answer of a player. | The port becomes "any ADK node that outputs the phase response". The response models stay. |
| `models/structured.py` | 105 | `StructuredTaskAgent` runs the judge and the word generator in a `Runner` and session of their own. | `ctx.run_node(agent)` inside the game run, and ADK's classifier for the judge. |
| `judge/llm_judge.py`, `judge/base.py` | 212 | They hold `JudgeProtocol`, the judge prompts and the structured answer. | ADK's `BaseClassifier` with `Binary` questions (`google.adk.labs.classifiers`). |
| `ports/` | 225 | The event bus and game store feed the CLI and the trace plugin. | The CLI reads the events of `runner.run_async`, and the plugin reads session state. |
| `players/fake.py` | 254 | Scripted and random players are used only by tests. | They move to `tests/` and plug in as function nodes. |

About 2,100 lines of `src/` shrink to an estimated 600 to 700. The engine, prompts,
catalog, word picker, telemetry setup, API app and frontend stay as they are.

## 3. Target design

### 3.1 The game lives in session state

`Game` is already event sourced: its constructor takes `config`, `secret`, `seats` and
`events`. Two small additions make it a state value: `game.snapshot()` returns those four
parts as JSON, and `Game.load(snapshot)` rebuilds the game. Every node loads the game from
`ctx.state["game"]`, and the nodes that change it write it back. The request stays in
`ctx.state["game:request"]` as today.

This removes `GameSessions`, `GameSession`, the store, the "already played" bookkeeping
(it becomes `if "game" in ctx.state`) and the cleanup code for cancelled runs. It also
makes the session the complete record of a game, so a persistent session service gives
persistence later without new code.

### 3.2 The workflow

```
START → setup → next_turns ──turn──→ play_turn → apply_turns ─┐
                   ▲   └──over──→ finish                       │
                   └───────────────────────────────────────────┘
```

All five nodes are plain functions wrapped with `@node`. The sketch below shows the shape
and leaves out docstrings and error handling.

```python
@node(rerun_on_resume=True)
async def setup(ctx: Context) -> AsyncGenerator[Event]:
    # Resolves the word (running the generator agent as a child node when asked),
    # creates the game, writes it to state and yields its first events.

@node
def next_turns(ctx: Context) -> Event:
    # The engine decides: one seat in sequential phases, all pending seats in parallel
    # phases. Starts those turns and yields their `turn_started` events.
    return Event(output=[TurnRequest(...)], route="turn")  # Or route="over".

@node(parallel_worker=True, rerun_on_resume=True)
async def play_turn(ctx: Context, node_input: TurnRequest) -> TurnResult:
    # Runs the seat's agent as a child node, checks the answer against the rules and the
    # judge, asks once more with the reason when it is rejected. Never changes the game.

@node
def apply_turns(ctx: Context, node_input: list[TurnResult]) -> Generator[Event]:
    # Applies the results in seat order, writes the game back, yields the new events.
```

- The engine still owns the flow. `next_turns` only asks `game.pending_seats` and
  `game.is_sequential`, and `apply_turns` only calls engine methods.
- Asking and applying stay separate steps, as the code style asks: `play_turn` does I/O
  and returns data, `apply_turns` changes the game. Parallel votes are applied in seat
  order because the parallel worker returns results in input order.
- The dispatch from response type to engine method moves onto the engine as
  `game.submit(seat=..., response=..., ...)` and `game.rejection(seat=..., response=...)`.
  For that the per-phase response models (`ClueResponse` and the others) move from
  `players/base.py` to `engine/responses.py`. They are plain data and need no ADK.
- `finish` yields the last events. The graph no longer has a node per phase, which is the
  one visible change (see §6, decision A).

### 3.3 Players are plain `LlmAgent`s

`play_turn` builds the agent of its seat and phase and runs it with
`ctx.run_node(node(agent, retry_config=..., timeout=...), node_input=task)`.

```python
LlmAgent(
    name=f"player_{seat}_{phase}",          # The author the frontend already parses.
    model=adk_model(entry),                 # Cached per catalog entry.
    static_instruction=renderer.system(),   # Keeps the Claude Sonnet workaround.
    instruction=view_instruction(seat),     # Provider: loads the game from state and
                                            # renders `game.view_for(seat)`.
    include_contents="none",
    output_schema=PHASE_RESPONSE_TYPES[phase],
    generate_content_config=generate_content_config(entry=entry, phase=phase),
    before_model_callback=None if entry.supports_structured_output else drop_schema,
    after_model_callback=record_usage,      # A closure over a list local to the turn.
)
```

- The view is rendered from state by the instruction provider, the documented way to give
  an agent dynamic context. The instance attributes `view`, `usages` and
  `failed_response` of `AdkPlayer` disappear, and so does the class.
- Schema errors and broken streams are retried by `RetryConfig(max_attempts=3)` on the
  node instead of the hand written loop over error codes. The prototype confirmed that a
  `ValidationError` of `output_schema` triggers the retry. Rate limits and server errors
  stay with the model clients in `models/factory.py`, as today.
- Token usage still reaches the engine for the budget (D29). The `after_model_callback`
  appends to a list that `play_turn` owns and returns in its `TurnResult`.
- The player port becomes "a node that outputs the phase response". `game_workflow` takes
  a small factory for that node. Production passes the `LlmAgent` factory. Tests pass a
  factory of function nodes around `RandomPlayer` and `ScriptedPlayer`, which move to
  `tests/`. A remote A2A player (future work) is also just a node.

### 3.4 The judge and the word generator

- The word generator becomes two plain `LlmAgent`s with `output_schema`, run by `setup`
  with `ctx.run_node`. Their events and spans then belong to the game run. Today they run
  in a hidden second `Runner`. `StructuredTaskAgent` is deleted.
- The judge is covered in §4. It is called from `play_turn` after the cheap code checks.
  Wrapping the decision in a small function node gives it ADK's `invoke_node` span, so
  the custom `judge_span` helper goes away.

### 3.5 CLI, telemetry and API

- `imposter play` builds the same `App`, runs it with ADK's `Runner` and prints the
  engine event found in `custom_metadata` of each event, exactly what the frontend does.
  The bus, the store and `run_game` are deleted.
- `GameTracePlugin` stays (plugins are the ADK way to reach the root span) but reads the
  game from `invocation_context.session.state` instead of the store.
- The API app, the catalog route, the trace route and IAP middleware do not change.

## 4. The judge on ADK classifiers and the Gemini Decisions API

### 4.1 Findings

- Google released the Gemini Decisions API on 11 November 2026 with the model
  `gemini-decision-1`. One request carries a shared input and 1 to 1,000 typed questions:
  `noul` (yes or no), `choice` and `score`. A `noul` answer is a calibrated probability
  `P(true)` between 0.01 and 0.99 plus a confidence. The model writes no text, so there
  is no rationale. Reported price is USD 0.10 per million input tokens with free output,
  and reported latency is 150 to 250 ms. These numbers come from secondary sources,
  because the official pages were not reachable from the planning session.
- ADK already has the matching abstraction, marked experimental:
  `google.adk.labs.classifiers` with `BaseClassifier.classify(input, questions)`, the
  question types `Binary`, `Choice` and `Score`, an `LlmClassifier` that implements the
  interface on any `BaseLlm`, and a `ClassifierNode` that routes a workflow on an answer.
  It is present in the installed 2.13.0.
- ADK 2.14.1 ships classifier adapters for OpenAI's decisions API and for TypeSafe, but
  none for Gemini yet.
- The SDK support (`client.decisions.create`) is in `google-genai` 3.2 and later. ADK
  2.14.1 requires `google-genai<3`, so the two cannot be installed together today.
- Public sources say the API is on the Gemini Developer API only, with Google Cloud
  support announced as coming. The SDK code already builds Vertex paths for decisions
  (`/projects/{project}/locations/{location}/decisions`), so Vertex support looks
  planned. It needs a live check in the sandbox project.

### 4.2 Design

`JudgeProtocol` and `LlmJudge` are replaced by one small `Judge` class that holds a
`BaseClassifier` and asks two `Binary` questions. The code checks still run first.

```python
SAME_WORD = Binary(
    instructions="Does the guess name the same thing as the secret word?",
    criteria="Synonyms, spelling variants, other grammatical forms and translations "
    "count. Related but different ideas do not.",
)
answer = await classifier.classify(
    input={"secret_word": word, "guess": guess}, questions={"same_word": SAME_WORD}
)
```

- The verdict is `probability >= threshold`, with the threshold a named constant per
  question. `JudgeVerdict` keeps `verdict`, `confidence` and `judge_model`, and
  `rationale` becomes optional. Nothing in the engine events or the frontend reads it.
- A `RefusalAnswer` or an error gives the lenient verdict, as today.
- Step 1 uses `LlmClassifier(model=<Gemini Flash-Lite on Vertex>)`. This is the same
  model as today behind ADK's interface, with no new dependency and no API key.
- Step 2 adds `GeminiDecisionsClassifier(BaseClassifier)`, about 50 lines that post to
  the `decisions` REST endpoint with `httpx`, the way ADK's own OpenAI and TypeSafe
  adapters do. It maps `Binary` to `noul`. A setting picks the classifier. The adapter is
  dropped when ADK ships its own.
- A slow test runs both classifiers over a labelled list of clue and guess cases taken
  from the playtests and reports where they disagree. The thresholds are set from that.

### 4.3 Recommendation

Move to the classifier interface now, because it removes code regardless of the backend.
Add the Decisions adapter behind a setting and make it the default only once it works on
Vertex with ADC. Using it today would need a Developer API key in Secret Manager, which
breaks D5 (everything on Vertex, no API keys). If the faster and calibrated judge is
worth that exception for a demo, it is a one-line setting (see §6, decision C).

A later use that fits the API well: one request per finished game that scores the
leakiness of every clue with `score` questions, for the tournament statistics.

## 5. Steps

Each step is one PR that keeps `make check test` green and the seeded games identical.

| Step | Change | Deletes |
|---|---|---|
| 0 | Record the event logs of a few seeded games played by the current workflow with fake players as golden files. Every later step must reproduce them event for event. | Nothing is deleted. |
| 1 | Add `Game.snapshot`, `Game.load`, `Game.submit` and `Game.rejection`, and move the response models to `engine/responses.py`. `GameRunner` calls them. | The `match` blocks of `GameRunner` go. |
| 2 | Replace the judge with `Judge` on `LlmClassifier`, run from the turn. Add the labelled comparison test. | `judge/base.py`, `judge/llm_judge.py` and `judge_span` go. |
| 3 | Build the new workflow of §3.2 and the agent factory of §3.3 with the game in state. Move the fakes to `tests/` as function nodes. Reset a seat's partial answer in the frontend when its attempt fails (see §7). | `GameRunner`, `AdkPlayer`, `PlayerProtocol`, both `Node` subclasses and `GameSessions` go. |
| 4 | Run the word generator agents from `setup`. | `models/structured.py` goes. |
| 5 | Point the CLI at the runner's events and the trace plugin at session state. | `ports/` and most of `adk_runner.py` go. |
| 6 | Upgrade to ADK 2.14.x. Add `GeminiDecisionsClassifier` behind a setting and try it against Vertex and the Developer API. | Nothing is deleted. |
| 7 | Update `README.md` decisions D6, D7, D13, D25 and D32, `agents-and-orchestration.md`, `observability.md`, `models-and-judge.md`, the top-level docs and `CLAUDE.md`. | The outdated sections go. |

Steps 1 and 2 are independent and low risk. Step 3 is the large one. Steps 4 and 5 are
cleanups that step 3 makes possible. The docs of step 7 are updated in each PR for the
parts that PR changes, and step 7 is the final pass.

## 6. Decisions to confirm

- **A. One turn loop instead of a node per phase (changes D32).** Recommended. The cost:
  `adk web` draws a five-node loop instead of the phase graph, and the trace has
  `play_turn` step spans with `imposter.phase.name` attributes instead of one span per
  phase. Keeping phase spans is possible with a nested `Workflow` per phase around a
  router node, but the prototype showed that a nested workflow does not pass its route
  to the outer graph and changes the event author to the phase name, so it costs extra
  nodes and a frontend change.
- **B. The game in session state.** Recommended. The cost: every state write sends the
  whole event log, so the stream of a game carries roughly 0.5 MB more with four players
  and up to 2 MB with eight. If that matters, the log can be read from the engine events
  already stored in `ctx.session.events` instead, which the prototype confirmed works,
  and only `Game.load` and its callers change.
- **C. Decisions API before Vertex support.** Recommended to wait and run on
  `LlmClassifier` until the Vertex check passes.
- **D. Schema retries without the error text.** `RetryConfig` reruns the agent with the
  same input, so the model no longer sees why its JSON was rejected. Recommended to
  accept this. The rule retry (an invalid clue or vote is asked again once with the
  reason) stays, because it is game logic in `play_turn`.

## 7. Risks and how they are covered

- **Streamed text of a retried attempt.** A node retry keeps the same node path, and the
  frontend starts a new partial answer only on a new path. The frontend resets the
  seat's partial answer when it sees an error event of that player.
- **Retry scope.** `RetryConfig` without `exceptions` retries every failure, including
  permanent ones. Step 3 lists the exception names of schema errors and broken streams.
- **Cancelled runs.** Today a cancelled run appends `game_aborted` to a game nobody can
  read anymore. With the game in state a cancelled run just stops. The budget abort and
  failed nodes still produce their events.
- **Experimental classifier API.** `labs.classifiers` may change between ADK releases.
  Only the `Judge` class touches it.
- **Leak invariant.** The Hypothesis leak tests keep running on the pure engine with the
  fakes. A new test asserts that the instruction provider of seat N renders only
  `view_for(N)`.

## 8. What the prototype showed

A throwaway script with a fake streaming model ran the graph of §3.2 on ADK 2.13.0:
function nodes with a loop edge and routes, the game log in `ctx.state`, a
`parallel_worker` turn node, a plain `LlmAgent` with `output_schema` run through
`ctx.run_node(node(agent, retry_config=...))`, and SSE streaming. It confirmed that
partial events arrive with the agent's name as author, that sequential and parallel
steps work with the same three nodes, that results come back in input order, that an
answer failing the schema is retried by ADK, and that events yielded by one node are in
`ctx.session.events` when the next node runs.

## 9. Sources

- [Gemini Decisions API announcement](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/)
- [Getting started with the Gemini Decisions API in Python](https://medium.com/google-cloud/getting-started-with-the-gemini-decisions-api-in-python-d2b40093034f)
- [Gemini Decision 1: benchmarks, pricing and access](https://www.datacamp.com/blog/gemini-decision-1)
- [Graph workflows in ADK](https://cloud.google.com/blog/topics/developers-practitioners/graph-workflows-in-adk-everything-you-need-to-know)
- [ADK dynamic workflows](https://adk.dev/workflows/dynamic)
