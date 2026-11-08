# Running and inspecting games

The [README](../README.md#getting-started) covers installation and the first live game.
This guide describes the implemented web app, its streaming API, and ways to inspect a
run. The [cloud setup](setup.md) and [infrastructure](infrastructure.md) guides cover
deployment separately. Live games call paid models even when they run locally.

## Set up a game

`make dev` starts the API on port 8000 and Vite on <http://localhost:5173>. On the setup
screen, choose a word from a category, enter a custom word, or ask Gemini to generate one.
Word generation adds a model call. Assign models to 3–8 seats, choose the imposters or
shuffle those assignments, and drag the seat handles to change their order. The setup
screen validates the options before a game can start.

Identity options control whether seats use names, seat numbers, or model identities.
Advanced options include clue and discussion rounds, a public category, an imposter hint,
and the token budget. The token budget is an abort threshold, not a dollar-denominated
billing limit.

## Watch and replay

The board shows the current answer on the table, earlier clues and statements in each
player's column, and a transcript alongside it. Votes appear as ballots when they are
revealed together. The imposter's guess, the judge's verdict, and the outcome follow,
then a debrief compares players' earlier actions and reported reasoning with their
reflections after learning the truth.

The header shows the phase, token usage, estimated cost, and a Cloud Trace link when
available. Selecting a completed phase jumps to its end. Playback controls pause and
resume the display, step through responses and phases, pause after rounds, and change
speed. If playback falls behind the live game, it accelerates to catch up, while
**Go live** jumps to the newest state. Pausing playback does not pause model execution.

### Public and private information

The board starts with hidden information visible, also called god mode. This view shows
the word, roles, and reported private reasoning. Switch off **Show hidden info** in the
header's view settings to use audience mode. Audience mode hides the word and roles
until the outcome reveal, keeps votes hidden until voting ends, and omits private
reasoning and model thinking before the outcome, including while an answer is still
streaming. Once the outcome is revealed, private information becomes visible in this
mode too.

These are display choices for a trusted viewer. The browser still receives the underlying
events, including secrets, and exports contain game data that the audience view hides.
The toggle does not redact the API stream or protect secrets from someone inspecting
network traffic. Agents receive their own restricted `PlayerView` independently of
which display mode the viewer chooses.

### Save a replay

Export a game as JSON from the header, then import it from the setup screen to replay it.
An imported game replays recorded events instead of calling the models again. Treat
exports as sensitive because they can contain the secret word and private reasoning.

Keep the page open during a live game. Leaving it, closing the streaming request, or
stopping the game aborts the run. Playback is a view of buffered events, not a persistent
server-side job that can be resumed after disconnecting. Server sessions and games are
held in memory, so a server restart loses that state.

## Use the API

The backend extends ADK's API server with `GET /catalog`, which lists the available
models, word categories, and default lineup, and `GET /traces/{game_id}`, which returns
trace information. Starting a game takes two requests.

1. Create a session with `POST /apps/imposter/users/{user_id}/sessions`, putting the
   `GameRequest` in the initial state under `game:request`. The session ID is the game ID.
2. Call `POST /run_sse` for that session to start the game and read the server-sent events.
   Set `"streaming": true` to receive partial answers as well as completed turns.

Game events travel in ADK event custom metadata. A turn-started event identifies the
active seat before its answer arrives. The request stays open for the duration of the
game, and a disconnect cancels the run. See the [API implementation](../src/imposter/api/app.py)
and [stream design notes](plans/web-ui.md) for the contract. The current OpenAPI schema
can be exported without running a server or calling a model.

```sh
uv run imposter openapi --output openapi.json
```

`make api-client` uses that schema to regenerate `frontend/src/api/schema.ts` and removes
its intermediate schema file.

## Build and serve locally

```sh
make frontend
uv run imposter serve --telemetry none
```

The API serves `frontend/dist` at <http://localhost:8000> when the build exists, so the
frontend and API share one origin. `IMPOSTER_FRONTEND_DIR` can select another build
directory, and `IMPOSTER_ALLOW_ORIGINS` can add comma-separated allowed origins. Running
the server with telemetry disabled does not make live games offline or free.

### Run a container

The Dockerfile builds the frontend in a Node stage, installs the Python package with uv,
and serves both through uvicorn in a slim Python image. It listens on `$PORT`, which
defaults to 8080.

With Docker, `.env`, and local Application Default Credentials already set up, run
`make docker` to build the image and serve it at <http://localhost:8080>. The target
mounts the credentials read-only from
`~/.config/gcloud/application_default_credentials.json`. Override `ADC_FILE` if the file
is elsewhere. Starting a live game in the container uses those credentials and incurs
model charges just as a local game does.

## Tracing

The app supports `IMPOSTER_TELEMETRY=cloud`, `console`, or `none`, also selectable with
`--telemetry` on the `play` and `serve` commands. Without an explicit choice, setting
`GOOGLE_CLOUD_PROJECT` selects cloud export. `none` disables the app's telemetry setup,
not the model clients or their network calls.

With cloud export configured, a game becomes one Cloud Trace trace. ADK supplies the
workflow, phase, turn, and model-call spans, while the app attaches game attributes and
judge-decision spans. HTTP-attempt spans make retries after timeouts and rate limits
visible. The root span carries the lineup and outcome and stores a hash of the word
rather than its plaintext. The terminal prints a Trace Explorer link after a game when
available, and the board links through the trace endpoint.

### Prompt and completion capture

The app supplies these defaults unless the environment already sets them.

```sh
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

With cloud export, ADK writes model prompts and completions to Cloud Logging as events
linked to the trace and span. Keeping content out of span attributes does not keep it
out of logs. Prompts may contain the secret word, and completions may contain reported
private reasoning, so access to telemetry should match the sensitivity of the game data.

In Logs Explorer, filter the entries of a game using its trace ID.

```text
logName:"gen_ai.client.inference.operation.details" trace="<trace id>"
```

`make adk-web` opens the ADK developer UI with cloud telemetry enabled by that target.
Its graph shows the workflow path and phase of the selected event. Starting a new game
there makes real model calls, just as the terminal and web board do. The
[observability design notes](plans/observability.md) describe the span hierarchy and
identity attributes in more detail.
