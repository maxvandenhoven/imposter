# Imposter

LLM agents from different model families (Gemini, Claude, open models on Vertex AI) play
the social deduction game [Imposter](https://imposter.app/) against each other. A demo for
exploring Google's Agent Development Kit (ADK), deployment on GCP (Cloud Run, IAP,
Terraform) and tracing (OpenTelemetry, Cloud Trace).

## Play a game

With `.env` set up (see below), `make play` runs a game in the terminal between a mixed
lineup of models and prints the outcome, the debrief and the token cost. Options go in
`ARGS`, for example `make play ARGS="--god --word lighthouse -p gemini-flash -p
claude-haiku -p gpt-oss"`, where `--god` also shows the secret word, the roles and every
private reasoning. `uv run imposter play --help` lists every option. `make adk-web`
starts the ADK developer UI, in which every new session plays a game.

## How a game runs

A pure game engine owns the rules and the event log, and decides every phase change. The
game is played by an ADK graph workflow with one node per phase (setup, clue,
discussion, vote, resolution, guess, outcome, debrief, done and aborted). The edges are
generated from the engine's table of phase transitions, so the graph shows every way a
game can go: the clue and discussion rounds are loop edges, a player who says the secret
word jumps straight to the outcome, and any phase in which players act can be aborted.
Each node plays its phase through the players, publishes the new game events and routes
to the phase that the engine moved to.

In the ADK developer UI (`make adk-web`), the graph shows the path a game took and
highlights the phase of the selected event.

![The phase graph of a finished game in the ADK developer UI](docs/images/adk-web-phase-graph.png)

## Tracing

Every game is one trace in Cloud Trace. ADK traces the workflow and every node, so the
trace has a root span for the game and a span per phase and round. ADK also traces every
model call, with its token usage. The app adds a span per player turn and a span per
judge decision, and the model calls of the players nest under their turn. The root span
carries the lineup and the outcome, and the secret word only as a hash, so a list of traces does not spoil it. `make play` prints the Trace
Explorer link of the game when it ends.

The prompts and completions are logged by ADK itself, with no code of ours: three
environment variables (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY`,
`ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` and
`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`) make ADK write one Cloud
Logging entry per model call, with the prompt, the answer and the tokens, and the trace
and span id of the call. The app sets them as defaults. In Logs Explorer, the query
`logName:"gen_ai.client.inference.operation.details" trace="<trace id>"` lists the
entries of one game.

Traces go to Cloud Trace when `GOOGLE_CLOUD_PROJECT` is set. `IMPOSTER_TELEMETRY` (or the
`--telemetry` option) chooses `cloud`, `console` to print the spans in the terminal, or
`none`.

## Design and setup

The design notes and decisions behind the app are in [`docs/plans/`](docs/plans/README.md).

To set up the app's infrastructure in the GCP sandbox project, follow [`docs/setup.md`](docs/setup.md).
[`docs/infrastructure.md`](docs/infrastructure.md) documents what is created in GCP, why,
and how it connects.
