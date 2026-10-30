# Agents and orchestration

## ADK setup

- Dependency: `google-adk[gcp,otel-gcp]` (version 2.x, pinned in `uv.lock`), plus
  `litellm` for non-Gemini models.
- Vertex AI mode via environment: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`. Credentials are ADC locally and
  the Cloud Run service account when deployed. No API keys.
- `src/imposter/agent.py` exposes a `root_agent` (the game workflow with a default
  request) so `adk web src` (`make adk-web`) lists the `imposter` app, draws the phase
  graph and plays one game per new session. `adk web` takes the directory that contains the agent packages, so it
  is `src`, not `src/imposter`.
- Before writing code, read the ADK cheatsheet (the `google-agents-cli-adk-code` skill) and
  check exact signatures in the installed package. The custom layout here replaces
  `agents-cli scaffold`; borrow from scaffolded templates where useful (telemetry setup,
  Dockerfile), but do not let tools own files that Terraform or this layout own.

## How the pieces fit

The engine is pure: it decides what is legal and what each seat may see, but never calls
a model. The players call models but know nothing of the rules beyond their own view.
`GameRunner` connects the two, one turn at a time:

```
 game ──view_for──▶ PlayerView ──take_turn──▶ PlayerResponse
  ▲                                                 │
  │                         runner.ask: checks, retry, judge (async, I/O)
  │                                                 ▼
  └─────── runner.apply: game.submit_* ◀─────── TurnResult
```

## GameRunner (`orchestration/runner.py`)

`GameRunner` holds the players (one per seat) and the optional clue and guess judges. The
turn logic is written once there and used by everything that runs a game: tests, the CLI
and the game workflow.

- `runner.ask(game=..., seat=...) -> TurnResult` is the only step that does I/O. It builds
  the seat's view, calls `take_turn`, runs the code checks and the clue judge, retries
  once with the rejection reason, and asks the guess judge about inexact guesses. It does
  not change the game.
- `runner.apply(game=..., result=...)` changes the game in place. It records usage (which
  may abort the game when the token budget runs out) and player errors, then submits the
  accepted output or the phase fallback (`pass` clue, empty statement, abstain vote,
  empty guess, empty reflection).
- `runner.play_step(game)` plays the next turn, or all turns of a parallel phase, and
  `runner.play(game)` repeats it until the game is over. In parallel phases (votes and
  debrief) every pending seat is asked at once with `asyncio.gather`, against the same
  game, and the answers are applied in seat order, so the event log does not depend on
  which model answered first.

## Game workflow (`orchestration/runner_workflow.py`)

A game is played by an ADK 2.x graph `Workflow` whose nodes are the game phases and whose
edges are every phase change the engine can make (README D32). `game_workflow(sessions=...)`
builds it from `PHASE_TRANSITIONS` in `utils/phases.py`, the single transition table that
`next_phase` and the secret word exit also read, so the graph cannot drift from the
engine. Every edge is routed by the name of the phase it enters, and rounds are loop
edges, so the graph is static and shows every config:

```
START → setup → clue ─┬─ clue          (next round)
                      ├─ discussion
                      ├─ vote          (discussion_rounds = 0)
                      └─ outcome       (secret word said)
         discussion ─┬─ discussion     (next round)
                     ├─ vote
                     └─ outcome        (secret word said)
         vote → resolution → guess → outcome → debrief → done
         clue, discussion, vote, guess, debrief ── aborted   (token budget, cancellation)
```

Each node is a `GamePhaseNode` (a subclass of ADK's `Node`). A node run plays one
segment, all events of one phase and round: it calls `runner.play_step(game)` until the
game leaves that phase and round, publishes the events of the segment to the
`EventBusProtocol` port, yields each as a content event (the event as JSON text, which
`adk web` shows), and routes to the phase of the next event with `Event(route=...)`. The
node never decides a transition itself (README D6): it follows the event log, and raises
when it is reached in a phase other than its own. Phases in which nobody acts
(resolution and outcome) are played by the engine as soon as the phase before them ends,
so their nodes only publish. The setup node creates the game from the `GameRequest` in
session state (or the default request, as in `adk web`), and the terminal nodes publish
the last events and close the bus. A second run in a session whose game was already
played yields a single message and plays nothing.

```
setup node:  game = setup.create_game(request from state, game_id = session id)
every node:  try:
                 check that the next unpublished event is in this node's phase
                 play_step until the game leaves this phase and round
                 publish the events of this phase and round
             except anything, including cancellation:
                 abort the game if it is not over, publish the rest, close the bus
                 raise
             yield a content event per engine event, then route to the next phase
```

Cancellation is handled in the node: when the task of the run is cancelled (for example
after an SSE disconnect), the game ends with a `game_aborted` event and subscribers see
the end of the stream. `run_game` finishes the game again in a `finally` block, which
does nothing when the node already did.

**Live objects.** ADK keeps node outputs and session state as JSON, but a `Game`, its
players and the bus are live objects. `GameSessions` keeps them per ADK session
(`GameSession`: the game, its `GameRunner` and how many events were published), and the
nodes look them up by session id. Nodes pass nothing to each other: the route is the
only output. This deviates from the Workflow API's replay and resumability model, which
would rebuild the game from state. A game cannot resume mid-way anyway, because players
are model calls and the engine has no resume from an event log yet.

**Per-seat fan-out.** Votes and debrief fan out over seats inside `GameRunner.play_step`
with `asyncio.gather`, not as `parallel_worker` nodes: players stay behind
`PlayerProtocol`, and one node per seat and phase would clutter the graph.

`orchestration/setup.py` holds `GameRequest` (the `GameConfig` plus the `WordOptions`)
and `GameSetup`, which chooses the secret word, creates the `Game` and seats an
`AdkPlayer` for every seat with the judge. Tests use a subclass that seats fake players.

The workflow holds no game rules: legality, tallying and outcome live in the `Game`, and
the turn logic in the `GameRunner`. It adds only what ADK, telemetry and the event bus
need. The names say what each part is: the `Game` is the game itself, the `GameRunner`
runs it, and the game workflow runs the `GameRunner` inside ADK, one node per phase.

`orchestration/adk_runner.py` wires ADK's own `Runner` with an `App` around the game
workflow and an `InMemorySessionService` (behind ADK's `BaseSessionService`, swappable
later), and creates one session per game (`session_id = game_id`). The `GameRequest` is
passed in the initial state under `game:request`. `run_game(request=..., setup=...,
bus=..., store=...)` is the coroutine the CLI uses and the API will use: subscribe to the
bus with the game id to follow the game while it runs.

**In `adk web`.** The dev UI draws the graph with ADK's workflow visualizer, with route
names on the edges, and highlights the path of a game and the node of the selected event.
Routing nodes carry a "no default" mark, because no edge has a `__DEFAULT__` route: every
transition is explicit. ADK's older `/dev/apps/{app}/graph` endpoint (`agent_graph.py`)
fails for workflows in ADK 2.13 because it reads a `_graph` attribute that `Workflow` no
longer has. The UI does not use it.

**`GameRunnerAgent`.** `orchestration/runner_agent.py` keeps the earlier custom
`BaseAgent`, which plays the whole game in one `_run_async_impl` loop. Tests play the
same seeded games through both and compare the event logs, including the secret word
exit, the budget abort and cancellation. Nothing else uses it, and it can be deleted
once the workflow has been used for real games for a while.

## Player interface

```python
class PlayerProtocol(Protocol):
    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse: ...
```

- The view carries the phase, round and limits, so the only extra input is the reason a
  previous attempt in the same turn was rejected.
- `PlayerResponse` wraps one of the structured responses below as `output`, plus `usage`
  (`TurnUsage`: input, output and thinking tokens, model id) and an optional `error`. A
  player that gives up returns `output=None` with an error, and the runner applies the
  phase fallback, so the fallbacks live in one place.
- `PHASE_RESPONSE_TYPES` maps each phase to its response type, for structured output.
- Implementations: `AdkPlayer` (real), `ScriptedPlayer` (tests: returns canned responses),
  `RandomPlayer` (tests and offline demos). A future `A2aPlayer` calls a remote agent over
  the A2A protocol (`future-work.md`).

## AdkPlayer

- One `LlmAgent` per seat and phase, created from the model catalog entry
  (`models/factory.py`), because `output_schema` and `max_output_tokens` differ per phase.
  All agents of a seat share one ADK model object. `include_contents='none'` so no
  conversation history is shared between players or turns.
- The instruction is an instruction provider (a callable on ADK's readonly context) that
  renders the prompt for this seat from the `PlayerView` it was given, written to session
  state under `player:{seat}:view` with the `state_delta` of the call. Session state is a
  hand-over to the instruction provider, not a second store: the engine stays the only
  owner of game state. Nothing else in state is rendered.
- A short fixed `static_instruction` (`prompts/system.md`) is the system instruction,
  which makes ADK send the rendered instruction as user content. Claude Sonnet refuses
  the game instruction as a system prompt but plays fine with it as a user message.
- Output: every agent has the response type as `output_schema` and an `output_key`, so
  ADK validates the answer and stores the parsed result in session state. Models whose
  catalog entry has `supports_structured_output: false` get the schema removed from the
  request by a `before_model_callback` and are asked for JSON in the task instead. On a
  validation error the player asks once more with the error message (ADK has no
  re-prompt for schema errors). An `after_model_callback` records the tokens of every
  call, including calls whose answer was invalid. A second failure produces the
  phase fallback (`pass` clue, empty statement, abstain vote, empty guess) and a
  `player_error` event. Claude Sonnet and `gpt-oss` use JSON in the prompt (see
  `models-and-judge.md`).
- The agent is called with a fresh user message per turn (the task). Each `AdkPlayer`
  runs its agents with its own ADK `Runner` and `InMemorySessionService`, with one
  session per game and phase (ADK warns about events from agents its runner does not
  know). The players are not nodes or sub-agents of the game workflow: that would tie
  `PlayerProtocol` to ADK's invocation context. Their ADK spans still nest under the
  node of the phase, because OpenTelemetry context travels with the asyncio task
  (checked in WP 15, see `observability.md`).

### Structured responses

| Phase | Schema |
|---|---|
| Clue | `{clue: str, private_reasoning: str}` |
| Discussion | `{statement: str, private_reasoning: str}` |
| Vote | `{vote_for: str, private_reasoning: str}` (display name of another player) |
| Guess | `{guess: str, private_reasoning: str}` |
| Debrief | `{reflection: str}` (about 150 words, covering clues, statements and vote) |

### Scratchpad

The scratchpad is part of the `PlayerView`: a list of `{phase, round, action,
private_reasoning}` entries that `Game.view_for` derives from the seat's own clue,
statement, vote and guess events. It never holds another seat's entries, and a vote
appears only once the votes are revealed (covered by the leak tests). Players keep no
memory of their own between turns.

## Prompts

`players/prompts/` holds Markdown templates (Jinja2):

- `rules.md`: the game rules in plain language, the same for everyone.
- `role_civilian.md`, `role_imposter.md`: role, goal and strategy nudge. Civilian: "prove
  you know the word without making it guessable for the imposter". Imposter: "blend in,
  infer the word from the clues, do not reveal you lack it".
- `transcript.md`: the game so far from the view: players, category and hint, clues,
  statements, revealed votes, the reveal and the seat's own scratchpad.
- `phase_clue.md`, `phase_discussion.md`, `phase_vote.md`, `phase_guess.md`,
  `phase_debrief.md`: the task and limits (word caps). They include `response.md`, which
  adds the retry reason and the JSON schema when native structured output is not used.
- `system.md`: the fixed system instruction (see AdkPlayer).
- `persona.md` slot (empty in v1, see `future-work.md`).

`players/prompt.py` (`PlayerPromptRenderer`) renders them: the instruction is `rules.md`,
`persona.md`, the role and `transcript.md`, and the task is the phase template. Snapshots
of every phase and role live in `tests/players/snapshots/` (`UPDATE_SNAPSHOTS=1` rewrites
them).

Rendered prompts are part of the leak tests: the imposter's rendered prompt never contains
the word.

## Concurrency, failures, limits

- Clues, discussion and guesses are sequential; votes and debrief run with
  `asyncio.gather`.
- Every LLM call: 60 s timeout, up to 2 retries with exponential backoff and jitter on 429
  and 5xx. The model clients do this (`models/factory.py`): `Gemini(retry_options=...)`
  with an HTTP timeout, and `LiteLlm(num_retries=..., timeout=...)`. Below ADK the status
  code is still known, so only transient errors are retried. After the last failure: phase fallback and a `player_error` event; the turn
  span gets error status. The game continues.
- `max_output_tokens` per phase (clue small, discussion and debrief larger) from config.
- Per-game token budget (default 200k, input + output + thinking). When exceeded, the
  engine moves to `ABORTED` with a `game_aborted` event and the reason.
- Cancellation: when the SSE client disconnects, the game task is cancelled and the game
  marked aborted (see `web-ui.md` for the keep-alive rules).

## Ports

`ports/` contains protocols and in-memory adapters, so persistence can be added without
touching the engine or orchestration:

- `GameStoreProtocol`: `save(game)`, `get(game_id) -> Game | None`,
  `list_recent(limit)`. Adapter `InMemoryGameStore`, a dict. A `Game` changes in place, so
  the in-memory store saves it once at creation. A persistent adapter would save it after
  every step, or store the event log instead.
- `EventBusProtocol`: `publish(game_id=..., event=...)`, `subscribe(game_id=...,
  from_seq=0) -> AsyncIterator[GameEvent]` which first replays buffered events then tails
  new ones, `close(game_id)`. Adapter `InMemoryEventBus`, a per-game buffer plus an
  `asyncio.Event` that is set and replaced on every change. `publish` and `close` are
  synchronous, so a workflow node can call them in its `except` block after a
  cancellation.
- ADK `BaseSessionService`: `InMemorySessionService` now; `DatabaseSessionService` or
  Vertex AI sessions later.

Future adapters (`future-work.md`): a Firestore game store and event log, and a Pub/Sub
event bus for multiple instances.
