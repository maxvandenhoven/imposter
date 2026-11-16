# API and event stream

This page is the reference for the HTTP API in `src/imposter/api/` and for the stream
of events a client reads while a game plays. The web app in `frontend/` is one such
client ([`frontend.md`](frontend.md)), and the CLI reads the same events in process.

## Routes

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
| `GET` | `/traces/{game_id}` | Ours: `{"url": ...}`, the Trace Explorer link of the game's run once it started, or `null` when traces are not sent to Google Cloud. The trace plugin of `agent.py` notes the trace id of each run |
| `GET` | `/health` | Liveness |
| `GET` | `/` | Ours: the built frontend, from `IMPOSTER_FRONTEND_DIR` or `frontend/dist`, when it exists. Mounted after every API route, so unknown API paths stay 404 |

ADK's other routes (artifacts, memory, `/list-apps`, `/run`) are there too and unused.

## Lifecycle of a game

The game runs inside the `/run_sse` request: it starts when the request
comes in and ends with the stream. When the client goes away, ADK cancels the run and
the game stops where it is. Running inside the request keeps CPU allocated under the
request-based billing of Cloud Run. There is no reconnect to a running game. The game is a snapshot in the state of
its session, so a second run of a finished session plays nothing, and a second run of a
session whose run stopped early plays the game on from the last saved step (the
frontend does not use this yet). A finished game can be loaded from its session.
Invalid options fail when the run starts, with an error event (`errorCode`,
`errorMessage`) in the stream.

## Reading the stream

Each SSE `data:` line is one ADK event as JSON (camelCase
fields). A client needs three kinds:

- **Engine events.** Events with `customMetadata.game_event` carry one engine event (the
  same JSON as the event log of [`game-rules.md`](game-rules.md#events), with `type`, `seq`, `phase`, `round` and the fields of its
  type), in `seq` order without gaps. A `turn_started` event (with `seat`) is sent before
  the player is asked, so it can drive a "thinking" indicator. The answer arrives as the
  engine event of the phase (`clue_given`, `statement_made`, `vote_cast`, `guess_made`,
  `reflection`) after the turn, together with `usage` and any `player_error`.
- **Token deltas.** Events with `partial: true` from author `player_{seat}_{phase}`
  carry the next chunk of the answer being written in `content.parts[].text`. Parts with
  `thought: true` are the model's native thinking, which a client can hide. The text is
  the JSON answer, for example `{"clue": "yel`, so a partial JSON parser shows `clue`,
  `statement` and `private_reasoning` as they grow. An attempt ends with a non-partial
  event of the same author: the full answer, or an `errorCode` event when it failed.
  ADK retries a failed attempt under the same `nodeInfo.path`, and a new attempt after
  a rejected answer gets a new path, ending in `player_{seat}_{phase}@{attempt}`. So a
  client starts an answer over after an attempt ended or when a new path appears.
  Chunk size depends on the model: Gemini sends a few large chunks, Claude and
  `gpt-oss` many small ones.
- **Errors.** An event with `errorCode` from author `game_runner` means the run failed,
  for example on invalid options, and ADK ends the stream with a last line of the form
  `{"error": "...", "error_details": {...}}`. An `errorCode` event from a
  `player_{seat}_{phase}` author is one failed model attempt, which the game handles: it
  asks again or falls back, and a `player_error` engine event says so.

Everything else can be ignored: the final event of each model call with its `output`,
the outputs of the nodes, routing events and the `stateDelta` of an event, which holds
the snapshot of the game that the server keeps in the session. Partial events are not stored in the
session, so a finished game loads without them.

The server sends every event with its private fields, and the session state holds the
secret word too. Audience mode hides them in the browser. That is acceptable because IAP
limits access to the people the owner lists.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `IMPOSTER_TELEMETRY` | `cloud` when `GOOGLE_CLOUD_PROJECT` is set, otherwise `none` | Where traces go: `cloud`, `console` or `none` ([`observability.md`](observability.md)). |
| `IMPOSTER_FRONTEND_DIR` | `frontend/dist` | The directory of the built web app, which is served at `/` when it exists. |
| `IMPOSTER_ALLOW_ORIGINS` | empty | Extra browser origins, separated by commas. ADK only accepts browser requests whose `Origin` is the server's own, so a proxy on another origin needs to be listed. |
| `IMPOSTER_DEV_USER` | empty | The user recorded on traces when no IAP header is present. |
| `GEMINI_API_KEY` | empty | The API key that makes the judge use the Gemini Decisions API ([`architecture.md`](architecture.md#judge)). |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI` | see `.env.example` | The Vertex AI settings of the Google clients. |

`imposter serve` runs uvicorn with the app factory (`imposter.api.app:create_app`), and
`make dev` runs it with reload.

## Why there are no game routes

The game already runs as an ADK app with the request in session state, and ADK's server
streams its runs over SSE and cancels a run when its client leaves. Routes of the app's
own would add a second event stream with replay and reconnect logic that ADK does not
need. What that gives up is reconnecting to a running game.

## What fails

| Symptom | Cause |
|---|---|
| The stream starts with an `errorCode` event from `game_runner` and ends with an `{"error": ...}` line | The request in the session state is invalid or missing, for example fewer than three players or an unknown word mode. |
| `player_error` engine events with `player failed: ...` | A model call of that seat failed after its retries. The game goes on with the fallback of the phase. |
| The stream ends with a `game_aborted` engine event | The game passed its token budget. |
| `POST /run_sse` is refused with status 403 | The `Origin` of the browser is not the server's own and is not in `IMPOSTER_ALLOW_ORIGINS`. |
| `GET /traces/{game_id}` returns `{"url": null}` | Traces are not exported to Google Cloud, or the run has not started. |

