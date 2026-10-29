# Agents and orchestration

## ADK setup

- Dependency: `google-adk[gcp,otel-gcp]` (version 2.x, pinned in `uv.lock`), plus
  `litellm` for non-Gemini models.
- Vertex AI mode via environment: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`. Credentials are ADC locally and
  the Cloud Run service account when deployed. No API keys.
- `src/imposter/agent.py` exposes a `root_agent` (a `GameRunnerAgent` with a default
  request) so `adk web src` (`make adk-web`) lists the `imposter` app and plays one game
  per new session. `adk web` takes the directory that contains the agent packages, so it
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
and the ADK agent.

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

## GameRunnerAgent (custom `BaseAgent`)

`orchestration/runner_agent.py` defines `GameRunnerAgent(BaseAgent)`, the ADK face of a
`GameRunner`. Its `_run_async_impl` plays the game step by step with the runner, yields
an ADK `Event` for every new engine event (the event as JSON text, so `adk web` and the
ADK runner see progress) and publishes each engine event to the `EventBusProtocol` port.
Phase and turn spans follow with the tracing work package.

```
game = setup.create_game(request from session state, game_id = session id)
runner = setup.runner_for(game)
try:
    loop:
        publish and yield the events not seen yet
        if game.is_over: break
        await runner.play_step(game)
finally:
    abort the game if it is not over, publish the rest, close the bus
```

The `finally` block covers cancellation: when the task of the run is cancelled (for
example after an SSE disconnect), the game ends with a `game_aborted` event and
subscribers see the end of the stream. A second run in a session whose game was already
played yields a single message and plays nothing.

`orchestration/setup.py` holds `GameRequest` (the `GameConfig` plus the `WordOptions`)
and `GameSetup`, which chooses the secret word, creates the `Game` and seats an
`AdkPlayer` for every seat with the judge. Tests use a subclass that seats fake players.

The `GameRunnerAgent` holds no game rules: legality, tallying and outcome live in the
`Game`, and the turn logic in the `GameRunner`. It adds only what ADK, telemetry and the
event bus need. The names say what each part is: the `Game` is the game itself, the
`GameRunner` runs it, and the `GameRunnerAgent` runs the `GameRunner` inside ADK.

`orchestration/adk_runner.py` wires ADK's own `Runner` with the `GameRunnerAgent`, an
`InMemorySessionService` (behind ADK's `BaseSessionService`, swappable later), and creates
one session per game (`session_id = game_id`). The `GameRequest` is passed in the initial
state under `game:request`. `run_game(request=..., setup=..., bus=..., store=...)` is the
coroutine the CLI uses and the API will use: subscribe to the bus with the game id to
follow the game while it runs.

ADK's graph `Workflow` API (2.x) was considered; the imperative `BaseAgent` reads more
naturally for configurable round counts and per-player fan-out (README D32).

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
  know). The players are not sub-agents of the `GameRunnerAgent`: that would tie
  `PlayerProtocol` to ADK's invocation context. Their ADK spans still nest under the
  game, because OpenTelemetry context travels with the asyncio task (checked in WP 07).

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
  synchronous, so the agent can call them in its `finally` block after a cancellation.
- ADK `BaseSessionService`: `InMemorySessionService` now; `DatabaseSessionService` or
  Vertex AI sessions later.

Future adapters (`future-work.md`): a Firestore game store and event log, and a Pub/Sub
event bus for multiple instances.
