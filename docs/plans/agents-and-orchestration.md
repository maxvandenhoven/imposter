# Agents and orchestration

## ADK setup

- Dependency: `google-adk[gcp,otel-gcp]` (version 2.x, pinned in `uv.lock`), plus
  `litellm` for non-Gemini models.
- Vertex AI mode via environment: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`. Credentials are ADC locally and
  the Cloud Run service account when deployed. The one API key is the optional one of
  the judge's Gemini Decisions API (`models-and-judge.md` §Judge).
- `src/imposter/agent.py` exposes a `root_agent` (the game workflow with a default
  request) so `adk web src` (`make adk-web`) lists the `imposter` app, draws the turn
  loop and plays one game per new session. `adk web` takes the directory that contains the agent packages, so it
  is `src`, not `src/imposter`.
- Before writing code, read the ADK cheatsheet (the `google-agents-cli-adk-code` skill) and
  check exact signatures in the installed package. The custom layout here replaces
  `agents-cli scaffold`; borrow from scaffolded templates where useful (telemetry setup,
  Dockerfile), but do not let tools own files that Terraform or this layout own.

## How the pieces fit

The engine is pure: it decides what is legal and what each seat may see, but never calls
a model. The players call models but know nothing of the rules beyond their own view.
The game workflow connects the two with ADK primitives only: function nodes, a parallel
worker, session state and plain `LlmAgent`s (README D32).

```
 state["game"] ──load──▶ Game ──view_for──▶ PlayerView ──take_turn──▶ response
       ▲                                                                  │
       │                              play_turn: rules, retry, judge (async, I/O)
       │                                                                  ▼
       └──save── Game ◀── game.submit ◀── apply_turns ◀────────────── TurnResult
```

## Game workflow (`orchestration/workflow.py`)

`GameWorkflowBuilder` holds what the nodes need (the word resolver, the player seating,
the judge and an optional default request) and builds a `Workflow` of five function
nodes. Each node is a method of the builder, wrapped with `node(...)`:

```
START → setup → next_turns ──turn──→ play_turn → apply_turns ─┐
                   ▲   └──over──→ finish                       │
                   └───────────────────────────────────────────┘
```

| Node | What it does |
|---|---|
| `setup` | It reads the `GameRequest` from session state, chooses the secret word (running the word generator's agent as a child node when asked), creates the game and saves it. A session that already has a game keeps it. |
| `next_turns` | It asks the engine who acts next: one seat in sequential phases, every pending seat in parallel phases. It starts those turns and outputs the seats, routed to `play_turn`. When the game is over it routes to `finish`. |
| `play_turn` | It is a `parallel_worker`, so ADK runs it once per seat of the list, at the same time. It asks the seat's player, checks the answer against the rules and the judge, and asks once more with the reason when the answer is rejected. It only reads the game. |
| `apply_turns` | It gets the results in seat order and applies them: usage first (which may abort the game over the token budget), then player errors, then `game.submit`, which applies the answer or the fallback of the phase. |
| `finish` | It ends the run with a line on how the game ended, which `adk web` shows. |

Why it looks like this:

- **The engine decides.** No node decides a transition (README D6). `next_turns` only
  asks `game.pending_seats` and `game.is_sequential`, and phases without players
  (resolution, outcome) are played by the engine when the phase before them ends. One
  loop therefore plays every phase and every config.
- **The game lives in session state.** `Game` is event sourced: `game.snapshot()` is its
  setup plus its event log, and `Game.load` rebuilds it. Every node loads the game from
  `ctx.state["game"]`, and the nodes that change it save it back. There are no live
  objects outside ADK, so there is no registry, no cleanup, and a persistent session
  service would persist games without new code. The cost is that every save puts the
  whole log in the `state_delta` of an event, about 0.4 MB over a game of four and
  1.2 MB over a game of eight with fake players.
- **Asking and applying are separate nodes.** `play_turn` does the I/O and returns a
  `TurnResult`, and `apply_turns` changes the game. The turns of a parallel phase run
  against the same game, and ADK returns their results in input order, so the event log
  does not depend on which model answered first.
- **Engine events are ADK events.** A node that changes the game yields one ADK event
  per new engine event, with the event as JSON in `custom_metadata["game_event"]` and as
  text in the content. The frontend, the CLI (`orchestration/play.py`) and the tests
  all read them from there.
- **Models never see state.** The state holds the secret word and every private
  reasoning, and it reaches the browser, which gets every engine event anyway and hides
  secrets in audience mode. A player's agent gets none of it: its instruction is
  rendered from `game.view_for(seat)` only, it has `include_contents='none'`, and the
  instruction is a provider function, so ADK fills no `{key}` placeholders from state.
  A workflow test plays a game on recording models and checks every request.

**Earlier versions.** The first version was a custom `BaseAgent` with one imperative
loop. The second was a graph with a custom `Node` subclass per phase, generated from the
engine's transition table, with the live `Game`, a `GameRunner` and an event bus kept in
a registry by session id. It drew the phases in `adk web` and gave a span per phase, but
needed about 1,400 lines of orchestration and player code around ADK. The loop of
function nodes plays the same seeded games event for event
(`tests/orchestration/snapshots/`).

## Player interface

```python
class PlayerProtocol(Protocol):
    async def take_turn(
        self,
        *,
        ctx: Context,
        view: PlayerView,
        record_usage: UsageRecorder,
        retry_reason: str | None = None,
    ) -> PhaseResponse: ...
```

- The view carries the phase, round and limits, so the only extra inputs are the ADK
  context of the turn node, a callback that takes the tokens of each model call, and
  the reason a previous attempt in the same turn was rejected.
- A player returns one of the structured responses below, or raises. `play_turn` turns
  an error into a `player_error` event, and `game.submit` applies the fallback, so the
  fallbacks live in one place.
- `PHASE_RESPONSE_TYPES` (`engine/responses.py`) maps each phase to its response type.
- `PlayerSeatingProtocol.player_for(game=..., seat=...)` decides who plays a seat.
  `LlmPlayerSeating` seats an `LlmPlayer` with the model of the seat's config. The tests
  seat `ScriptedPlayer` and `RandomPlayer` (`tests/fakes.py`). A future `A2aPlayer`
  calls a remote agent over the A2A protocol (`future-work.md`).

## LlmPlayer (`players/llm_player.py`)

- A turn builds one plain `LlmAgent`, named `player_{seat}_{phase}`, and runs it as a
  child node: `await ctx.run_node(agent, node_input=task)`. Running inside the game
  invocation is what makes streaming work: the agent's partial events go to the client
  of the game run as they come, and ADK puts the agent's spans below the turn.
- `include_contents='none'`, so no conversation history is shared between players or
  turns. The instruction is the prompt rendered from the `PlayerView` of the turn, and
  the task of the phase is the user message.
- A short fixed `static_instruction` (`prompts/system.md`) is the system instruction,
  which makes ADK send the rendered instruction as user content. Claude Sonnet refuses
  the game instruction as a system prompt but plays fine with it as a user message.
- The response type of the phase is the agent's `output_schema`, so ADK validates the
  answer and `ctx.run_node` returns it. Models whose catalog entry has
  `supports_structured_output: false` get the schema removed from the request by a
  `before_model_callback` and are asked for JSON in the task instead (Claude Sonnet and
  `gpt-oss`, see `models-and-judge.md`).
- ADK retries the agent: its `retry_config` allows three model calls when the answer
  misses the schema or the stream broke off midway. The retry sends the same request,
  without the error text. Other errors are final.
- An `after_model_callback` passes the tokens of every call to `record_usage`,
  including calls whose answer was invalid. In a streaming run it also sees each partial
  response, so only the final response counts. It raises on a response that came with an
  error (such as a safety block), because ADK would otherwise end the agent without an
  answer and without an error.

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
- `system.md`: the fixed system instruction (see LlmPlayer).
- `persona.md` slot (empty in v1, see `future-work.md`).

`players/prompt.py` (`PlayerPromptRenderer`) renders them: the instruction is `rules.md`,
`persona.md`, the role and `transcript.md`, and the task is the phase template. Snapshots
of every phase and role live in `tests/players/snapshots/` (`UPDATE_SNAPSHOTS=1` rewrites
them).

Rendered prompts are part of the leak tests: the imposter's rendered prompt never contains
the word.

## Concurrency, failures, limits

- Clues, discussion and guesses are sequential. Votes and debrief are parallel: ADK's
  parallel worker runs one `play_turn` per seat.
- Every LLM call: 60 s timeout, up to 2 retries with exponential backoff and jitter on 429
  and 5xx. The model clients do this (`models/factory.py`): `Gemini(retry_options=...)`
  with an HTTP timeout, and `LiteLlm(num_retries=..., timeout=...)`. Below ADK the status
  code is still known, so only transient errors are retried.
- Above that there are two more retries. ADK reruns the agent when the answer misses
  the schema or the stream broke (`RetryConfig` on the agent), and `play_turn` asks once
  more with the reason when the rules or the judge reject a valid answer.
- After the last failure: phase fallback and a `player_error` event. The turn span gets
  error status. The game continues.
- `max_output_tokens` per phase (clue small, discussion and debrief larger) from config.
- Per-game token budget (default 200k, input + output + thinking). When exceeded, the
  engine moves to `ABORTED` with a `game_aborted` event and the reason.
- Cancellation: when the client of `/run_sse` disconnects, ADK cancels the run. The game
  in state is then simply not over, and the root span gets error status (see
  `web-ui.md`).

## Sessions and persistence

Everything a game needs between nodes is in its ADK session: the request and the game
snapshot in state, and every non-partial event of the run. A client can load a finished
game with `GET /apps/imposter/users/{user_id}/sessions/{session_id}`. The session
service is `InMemorySessionService` now. `DatabaseSessionService` or Vertex AI sessions
would persist games without a change to the workflow (`future-work.md`).
