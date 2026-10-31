# Web UI and API

## API (ADK's API server, `src/imposter/api/`)

The backend is ADK's own API server (`get_fast_api_app`, what `adk api_server` runs)
serving the game app of `agent.py`, plus one route of ours. `api/app.py` builds it in
single agent mode (the package directory as `agents_dir`), with sessions in memory and
without ADK's dev UI. There are no game routes of our own: a game is an ADK session, and
playing it is an ADK run.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/catalog` | Ours: the models (id, display name, provider, logo, prices), the word categories (name and description, no words) and the default lineup |
| `POST` | `/apps/imposter/users/{user_id}/sessions` | Create a game: the body is `{"state": {"game:request": <GameRequest>}}`. The session id is the game id |
| `POST` | `/run_sse` | Play the game and stream its events. Body: `app_name`, `user_id`, `session_id`, `new_message` (any user message, for example "Play the game."), `"streaming": true` |
| `GET` | `/apps/imposter/users/{user_id}/sessions/{session_id}` | The session with every stored event, for a finished game |
| `GET` | `/health` | Liveness |

ADK's other routes (artifacts, memory, `/list-apps`, `/run`) are there too and unused.

**Lifecycle.** The game runs inside the `/run_sse` request: it starts when the request
comes in and ends with the stream. When the client goes away, ADK cancels the run and
the game is aborted. This keeps CPU allocated under request-based billing (README D14).
There is no reconnect to a running game: a second run of the session plays nothing and
says the game was already played. A finished game can be loaded from its session.
Invalid options fail when the run starts, with an error event (`errorCode`,
`errorMessage`) in the stream.

**Reading the stream.** Each SSE `data:` line is one ADK event as JSON (camelCase
fields). A client needs three kinds:

- **Engine events.** Events with `customMetadata.game_event` carry one engine event (the
  same JSON as the event log, with `type`, `seq`, `phase`, `round` and the fields of its
  type), in `seq` order without gaps. A `turn_started` event (with `seat`) is sent before
  the player is asked, so it can drive a "thinking" indicator. The answer arrives as the
  engine event of the phase (`clue_given`, `statement_made`, `vote_cast`, `guess_made`,
  `reflection`) after the turn, together with `usage` and any `player_error`.
- **Token deltas.** Events with `partial: true` from author `player_{seat}_{phase}`
  carry the next chunk of the answer being written in `content.parts[].text`. Parts with
  `thought: true` are the model's native thinking, which a client can hide. The text is
  the JSON answer, for example `{"clue": "yel`, so a partial JSON parser shows `clue`,
  `statement` and `private_reasoning` as they grow. Every attempt of a turn has its own
  `nodeInfo.path`, ending in `player_{seat}_{phase}@{attempt}`, so a client starts over
  when a new path appears (a retry). Chunk size depends on the model: Gemini sends a
  few large chunks, Claude and `gpt-oss` many small ones.
- **Errors.** An event with `errorCode` from author `game_runner` means the run failed,
  for example on invalid options, and ADK ends the stream with a last line of the form
  `{"error": "...", "error_details": {...}}`. An `errorCode` event from a
  `player_{seat}_{phase}` author is one failed model attempt, which the game handles: it
  asks again or falls back, and a `player_error` engine event says so.

Everything else (the final event of each model call with its `output`, the output of
each turn node, routing events) can be ignored. Partial events are not stored in the
session, so a finished game loads without them.

- The server sends **all** events including private fields; audience mode hides them in
  the browser. Acceptable because access is limited to the owner via IAP.
- Settings come from the environment: `IMPOSTER_TELEMETRY` (`observability.md`) and the
  Vertex AI variables of `.env.example`.
- `imposter serve` (CLI) runs uvicorn with the app factory
  (`imposter.api.app:create_app`), and `make dev` runs it with reload.

Why no API of our own: the game already runs as an ADK app with the request in session
state, and ADK's server streams its runs over SSE and cancels a run when its client
leaves. Own routes would add a second event stream, replay and reconnect logic that ADK
does not need. What that gives up is reconnecting to a running game.

## Frontend (`src/imposter/web/`)

- One `index.html`, one `app.js` (Alpine.js component, loaded from a pinned CDN version or
  vendored), `input.css` compiled to `tailwind.css` by the **standalone Tailwind CLI**
  (binary, no Node): `make css` locally, a build stage in the Dockerfile. The compiled CSS
  is not committed.
- Logos: small SVGs per provider in `web/logos/`.
- `fetch` with a stream reader for `/run_sse` (a `POST`, so not `EventSource`).
- Style: dark, "game night" look; cards per seat; subtle animations with Tailwind
  transitions/keyframes and Alpine `x-transition`. Works at laptop and projector sizes;
  phone layout is nice-to-have.

### Setup screen

Kept simple: the essentials up front, the rest under "Advanced".

- Word: tabs for *Random* (category dropdown), *Type* (text + optional category),
  *Surprise me* (generated).
- Players: list of seats with a model dropdown each, add/remove (3–8), "randomise
  lineup".
- Identity mode: segmented control (Seats / Names / Models).
- Toggles: public category, imposter hint.
- Advanced: clue rounds, discussion rounds, imposters, word caps, token budget,
  temperature override.
- Start → `POST /api/games`, then open the board and subscribe.

### Game board

- Seats in a circle or row: name, model logo (god mode or after reveal), role badge (god
  mode or after reveal), speaking indicator for the current turn.
- Timeline/transcript: clues appear as chips per round sliding in; discussion as speech
  bubbles; votes as a reveal sequence with arrows/counts; the imposter's guess and the
  judge verdict; an outcome banner.
- God mode: the word, roles, and each turn's private reasoning shown live as a
  "thought bubble" next to the public action.
- Header: phase indicator, running token and cost estimate, link to the trace in Cloud
  Trace, mode toggle (audience / god).
- Errors (`player_error`) shown inline as a small warning on the turn.

### Playback

All events are appended to an in-browser array (the timeline); the board renders the state
up to a **cursor**:

- **Live**: the cursor follows the newest event (default).
- **Step**: ◀ / ▶ buttons and arrow keys move one event; "next phase" jumps.
- **Autoplay**: steps at an adjustable speed (e.g. one event per 2 s).
- A badge shows "N events ahead" when behind live; a "Go live" button jumps back.
- The tab must stay open until the game finishes (it holds the SSE connection).

### Export and import

- **Export**: downloads `{config, events, exported_at, version}` as JSON.
- **Import**: loads such a file into the same board in playback mode, without a backend
  game. Useful as a demo fallback when live APIs fail.

### Debrief panel

After `game_finished`: per player, a card with role, model, clues, statements, vote, the
in-the-moment private reasoning at each turn and the after-the-fact reflection side by
side, plus tokens and cost.

## Testing

- API: FastAPI's `TestClient` against the app, with fake players in the game setup of
  `agent.py`: the catalog, ADK serving only the game app, and a game created as a
  session and streamed over `/run_sse` to the end. Streaming of model tokens is tested on
  the player with a fake model, and was checked against real models with `curl`.
- Frontend: no JS test framework in v1. Keep logic in `app.js` small and render from the
  event list; manual check list in the PR description of each UI work package.
