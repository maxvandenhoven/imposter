# Web UI and API

## API (FastAPI, `src/imposter/api/`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Static `index.html` (and `/static/*` for js, css, logos) |
| `GET` | `/api/catalog` | Models (display name, provider, logo) and categories |
| `POST` | `/api/games` | Create a game from a `GameConfig`, returns `game_id`. `409` if a game is already running (one at a time) |
| `GET` | `/api/games/{id}/events?from_seq=0` | SSE stream: replays buffered events, then live events. Starts the game on first subscribe |
| `POST` | `/api/games/{id}/abort` | Abort the running game |
| `GET` | `/api/games/{id}/export` | Full event log as JSON (also built client side) |
| `GET` | `/healthz` | Liveness |

- SSE with `sse-starlette` (or FastAPI's native SSE support if available in the pinned
  version). Each message: `id: <seq>`, `event: <type>`, `data: <json>`. Heartbeat comment
  every 15 s so proxies keep the connection open. `Last-Event-ID` is honoured on reconnect.
- The server sends **all** events including private fields; audience mode hides them in
  the browser. Acceptable because access is limited to the owner via IAP; note this in the
  code.
- The game runs as an `asyncio` task bound to the SSE connection: it starts on the first
  subscriber and is cancelled (game aborted) when the last subscriber has been gone for
  30 s. This keeps CPU allocated under request-based billing (README D14).
- Settings with `pydantic-settings` (`IMPOSTER_` prefix): project, locations, exporter,
  dev user, token budget, limits.
- `imposter serve` (CLI) runs uvicorn; `make dev` runs it with reload.

## Frontend (`src/imposter/web/`)

- One `index.html`, one `app.js` (Alpine.js component, loaded from a pinned CDN version or
  vendored), `input.css` compiled to `tailwind.css` by the **standalone Tailwind CLI**
  (binary, no Node): `make css` locally, a build stage in the Dockerfile. The compiled CSS
  is not committed.
- Logos: small SVGs per provider in `web/logos/`.
- Native `EventSource` for SSE.
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

- API: httpx `AsyncClient` against the app with `ScriptedPlayer`s and the in-memory bus:
  create game, stream events to the end, replay with `from_seq`, `409` on a second game,
  abort.
- Frontend: no JS test framework in v1. Keep logic in `app.js` small and render from the
  event list; manual check list in the PR description of each UI work package.
