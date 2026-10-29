# Agents and orchestration

## ADK setup

- Dependency: `google-adk[gcp,otel-gcp]` (version 2.x, pinned in `uv.lock`), plus
  `litellm` for non-Gemini models.
- Vertex AI mode via environment: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`. Credentials are ADC locally and
  the Cloud Run service account when deployed. No API keys.
- `src/imposter/agent.py` exposes a `root_agent` (a `GameMaster` with a default config) so
  `adk web src/imposter` works for poking at the agents during development. Single player
  agents can be tried there as well.
- Before writing code, read the ADK cheatsheet (the `google-agents-cli-adk-code` skill) and
  check exact signatures in the installed package. The custom layout here replaces
  `agents-cli scaffold`; borrow from scaffolded templates where useful (telemetry setup,
  Dockerfile), but do not let tools own files that Terraform or this layout own.

## GameMaster (custom `BaseAgent`)

`orchestration/game_master.py` defines `GameMaster(BaseAgent)`. Its `_run_async_impl`
drives the pure engine through the phases of `game-rules.md` and yields ADK `Event`s for
each engine event (so `adk web` and the ADK runner see progress). It also publishes each
engine event to the `EventBus` port.

```
for phase in engine.phases():
    with phase_span(phase):
        match phase:
            sequential phases (clue, discussion): for seat in seat order -> take_turn
            parallel phases (vote, debrief): asyncio.gather(take_turn for each seat)
            guess: for each imposter -> take_turn, then judge
        apply responses to engine -> engine emits events -> publish
```

The `GameMaster` holds no game rules itself: legality, tallying and outcome live in the
engine. It is the glue between engine, players, judge, event bus and telemetry.

`orchestration/runner.py` wires an ADK `Runner` with the `GameMaster`, an
`InMemorySessionService` (behind ADK's `BaseSessionService`, swappable later), and creates
one session per game (`session_id = game_id`). Game config is passed in the initial state.

ADK's graph `Workflow` API (2.x) was considered; the imperative `BaseAgent` reads more
naturally for configurable round counts and per-player fan-out (README D32).

## Player interface

```python
class Player(Protocol):
    seat: int
    async def take_turn(self, view: PlayerView, task: PlayerTask) -> PlayerResponse: ...
```

- `PlayerTask` names the phase and carries phase-specific instructions and limits.
- `PlayerResponse` wraps one of the structured responses below as `output`, plus `usage`
  (`TurnUsage`: input, output and thinking tokens, model id), `attempts` and an optional
  `error` when the player fell back to a default output.
- `players/driver.py` has `GameDriver`, a small in-process loop with the same turn logic
  as the `GameMaster` (one retry with the rejection reason, then the phase fallback), used
  by tests and offline demos until WP 06.
- Implementations: `AdkPlayer` (real), `ScriptedPlayer` (tests: returns canned responses),
  `RandomPlayer` (tests and offline demos). A future `A2aPlayer` calls a remote agent over
  the A2A protocol (`future-work.md`).

## AdkPlayer

- One `LlmAgent` per seat, created from the model catalog entry (`models/factory.py`),
  `include_contents='none'` so no conversation history is shared between players or turns.
- The instruction is an instruction provider (a callable on ADK's readonly context) that
  renders the prompt for this seat from the `PlayerView` stored in session state under
  `player:{seat}:view`. Nothing else in state is rendered.
- Output: native `output_schema` for models whose catalog entry has
  `supports_structured_output: true` (Gemini; check Claude via LiteLLM). Otherwise the
  prompt asks for JSON matching the schema, the player parses it with pydantic, and on a
  validation error retries once with the error message. A second failure produces the
  phase fallback (`pass` clue, empty statement, abstain vote, empty guess) and a
  `player_error` event.
- The agent is called with a fresh user message per turn (the task), through the same ADK
  runner/session so ADK spans and events nest under the game.

### Structured responses

| Phase | Schema |
|---|---|
| Clue | `{clue: str, private_reasoning: str}` |
| Discussion | `{statement: str, private_reasoning: str}` |
| Vote | `{vote_for: str, private_reasoning: str}` (display name of another player) |
| Guess | `{guess: str, private_reasoning: str}` |
| Debrief | `{reflection: str}` (about 150 words, covering clues, statements and vote) |

### Scratchpad

`player:{seat}:scratchpad` in session state, a list of `{phase, round, action,
private_reasoning}` entries. After each turn the player's own entry is appended. The
`PlayerView` includes only that seat's scratchpad. Session state keys are namespaced per
seat and never rendered for another seat (covered by the leak tests).

## Prompts

`players/prompts/` holds Markdown templates (Jinja2):

- `rules.md`: the game rules in plain language, the same for everyone.
- `role_civilian.md`, `role_imposter.md`: role, goal and strategy nudge. Civilian: "prove
  you know the word without making it guessable for the imposter". Imposter: "blend in,
  infer the word from the clues, do not reveal you lack it".
- `phase_clue.md`, `phase_discussion.md`, `phase_vote.md`, `phase_guess.md`,
  `phase_debrief.md`: the task, limits (word caps) and the JSON schema when native
  structured output is not used.
- `persona.md` slot (empty in v1, see `future-work.md`).

Rendered prompts are part of the leak tests: the imposter's rendered prompt never contains
the word.

## Concurrency, failures, limits

- Clues, discussion and guesses are sequential; votes and debrief run with
  `asyncio.gather`.
- Every LLM call: 60 s timeout, up to 2 retries with exponential backoff and jitter on 429
  and 5xx. After the last failure: phase fallback and a `player_error` event; the turn
  span gets error status. The game continues.
- `max_output_tokens` per phase (clue small, discussion and debrief larger) from config.
- Per-game token budget (default 200k, input + output + thinking). When exceeded, the
  engine moves to `ABORTED` with a `game_aborted` event and the reason.
- Cancellation: when the SSE client disconnects, the game task is cancelled and the game
  marked aborted (see `web-ui.md` for the keep-alive rules).

## Ports

`ports/` contains protocols and in-memory adapters, so persistence can be added without
touching the engine or orchestration:

- `GameStore`: `create(config) -> game_id`, `get(game_id)`, `update(game_id, ...)`,
  `list_recent()`. In-memory dict.
- `EventBus`: `publish(game_id, event)`, `subscribe(game_id, from_seq=0) ->
  AsyncIterator[GameEvent]` which first replays buffered events then tails new ones,
  `close(game_id)`. In-memory per-game buffer plus `asyncio.Condition`.
- ADK `BaseSessionService`: `InMemorySessionService` now; `DatabaseSessionService` or
  Vertex AI sessions later.

Future adapters (`future-work.md`): Firestore `GameStore` and event log, Pub/Sub
`EventBus` for multi-instance.
