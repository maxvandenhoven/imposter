# Observability

Goal: one game is one readable trace in Cloud Trace, filterable by model, role, phase and
identity mode, with full prompts and completions one click away in Cloud Logging.

## Setup

- ADK emits OpenTelemetry spans out of the box (`invoke_workflow`, `invoke_node`,
  `invoke_agent`, `generate_content` and tools, see §Span hierarchy). Export follows the
  programmatic GCP setup of ADK's tracing guide (https://adk.dev/observability/traces/):
  `telemetry/setup.py` (`setup_telemetry`) hands `get_gcp_exporters(...)` with tracing
  and logging enabled to `maybe_set_otel_providers`, which exports over OTLP to
  `telemetry.googleapis.com` with ADC. The guide enables tracing only, and we add the
  logging exporter because ADK's prompt and completion events are logs. As in the guide,
  the resource comes from `OTEL_SERVICE_NAME` (`imposter`) and
  `OTEL_RESOURCE_ATTRIBUTES`, which must carry `gcp.project_id`: without it the
  telemetry API rejects the spans (400). Cloud Monitoring metrics are left off.
- `setup_telemetry` also turns on OpenTelemetry's `aiohttp` client instrumentation, so
  each HTTP attempt of a model call is a `POST` span below `generate_content`, with its
  URL, status code and duration. The model clients retry timeouts, rate limits and server
  errors inside one call, and without these spans a slow call cannot be told apart from a
  retried one. google-genai and LiteLLM both send their async requests with `aiohttp`
  (not `httpx`, which ADK instruments on Agent Engine). `adk web` does not get these
  spans.
- `make adk-web` runs `adk web --otel_to_cloud`, the guide's way for the developer UI.
  `agent.py` sets the same defaults (`set_telemetry_defaults`), so games played there are
  traced and logged like CLI games.
- LiteLLM calls (Claude, open models) appear as spans too: ADK's `generate_content`
  span covers them, with token usage (checked in a real game), so no LiteLLM callback is
  needed.
- A streaming run (the API's `/run_sse` with `"streaming": true`) traces the same way: a
  model call is still one `generate_content` span with the tokens of the whole call, and
  the partial events of the stream add no spans. Checked in a real game with Gemini,
  Claude and `gpt-oss`.
- `setup_telemetry` is called once by the CLI and by the API app, before ADK builds the
  app, so ADK keeps our tracer provider. It returns the project, which the CLI uses to
  print the Trace Explorer link of the game.
- Exporter selection via `IMPOSTER_TELEMETRY`, `imposter play --telemetry` or
  `imposter serve --telemetry`: `cloud`
  (default when `GOOGLE_CLOUD_PROJECT` is set), `console` (spans to stderr), or `none`
  (tests, and the default without a project).

## Span hierarchy

The game runs as an ADK graph `Workflow` of function nodes
(`agents-and-orchestration.md` §Game workflow), so ADK emits the game, step and turn
levels of the trace itself. We add attributes to those spans and open spans of our own
only for judge decisions and for calls to the Gemini Decisions API, which ADK has no
span for. The hierarchy is pinned with fake players and a player on a fake model in
`tests/telemetry/test_spans.py`:

```
POST /run_sse                                    the API request, when served (FastAPI)
└─ invoke_workflow game_runner                   game: one per game (ADK, attributes ours)
   ├─ invoke_node setup                          creates the game
   │  └─ invoke_agent word_generator             only for a generated word or a hint
   ├─ invoke_node next_turns                     starts a turn, or all turns of a phase
   ├─ invoke_node play_turn                      step: the parallel worker (ADK)
   │  ├─ invoke_node play_turn                   turn: one per seat (ADK, attributes ours)
   │  │  ├─ invoke_agent player_0_clue           the player's agent, a child node of the turn
   │  │  │  └─ generate_content {model}          tokens, finish reason
   │  │  │     └─ POST                           one per HTTP attempt (aiohttp)
   │  │  └─ judge clue                           one per judge decision (ours)
   │  │     └─ decisions gemini-decision-1       the Decisions API call (ours), or
   │  │                                          generate_content of the Flash-Lite judge
   │  └─ invoke_node play_turn                   the other seats of a parallel phase
   ├─ invoke_node apply_turns                    applies the answers to the game
   ├─ invoke_node next_turns, play_turn, apply_turns, ...   the loop, once per step
   └─ invoke_node finish
```

The trace has no span per phase: the phase and round are attributes of every turn span.

What ADK sets, as of ADK 2.14:

- `invoke_workflow game_runner` (the root of a CLI game, below `POST /run_sse` when the
  API serves the game): `gen_ai.operation.name =
  invoke_workflow`, `gen_ai.conversation.id` (the session id, which is the game id) and
  `gen_ai.workflow.name`. It records the error when a node fails.
- `invoke_node {node}`: `gen_ai.operation.name = invoke_node`, `gen_ai.conversation.id`
  and `gcp.vertex.agent.associated_event_ids` (the ADK events the node run yielded). The
  parallel worker and each of its runs share the name `invoke_node play_turn`.
- `LlmPlayer` runs the agent of a turn as a child node of the turn (`ctx.run_node`),
  which opens `invoke_agent {agent}` and `generate_content {model}` below the turn. The
  word generator's agents run the same way below `setup`.
  `generate_content` carries `gen_ai.request.model`,
  `gen_ai.request.max_tokens`, `gen_ai.agent.name`, `gen_ai.usage.input_tokens` and
  `gen_ai.usage.output_tokens`, also for LiteLLM models (Claude, `gpt-oss`).

How our attributes and spans get there (`telemetry/spans.py`):

- **Game.** A node cannot reach the root span, but ADK runs the run callbacks of plugins
  inside it. `GameTracePlugin`, an ADK `BasePlugin` registered on the `App` (in the CLI
  and in `agent.py` for the API and `adk web`), notes the trace id before the run and
  sets the game attributes after it (or in `on_run_error_callback`), from the game in
  the state of the session. This keeps ADK's span as the root instead of adding a `game`
  span above it.
- **Turn.** The `invoke_node` span of a `play_turn` run is the current span inside it,
  so `mark_turn` sets the turn attributes on it and `record_turn` the outcome. The
  player's agent runs as a child node of the turn, so every attempt and the judge calls
  of the turn are below it, and the retry and the fallback only exist at this level. A
  plain OpenTelemetry span around the attempts would not work: ADK takes the parent of a
  child node's span from the node context, not from the current span. The tokens are not
  repeated on the turn: ADK sets
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` and
  `gen_ai.usage.reasoning.output_tokens` on every `generate_content` span, and the
  same numbers are in its log entry of the call.
- **Judge.** `Judge` opens `judge {kind}` (`judge_span`) around each decision. Most
  decisions are made by the code checks, which ADK does not see, and no span of a model
  call carries the verdict.
- **Decisions API.** `GeminiDecisionsClassifier` calls the API over plain HTTP, which
  neither ADK nor the Gen AI SDK instrumentation sees, so it opens a client span
  `decisions {model}` around each call, below the judge span.

Trace Explorer filters use `imposter.*` attributes rather than span names, because the
ADK names repeat.

Attributes (prefix `imposter.` for our own, OTel semantic conventions where they exist):

| Span | Attributes |
|---|---|
| game (`invoke_workflow game_runner`) | `imposter.game.id`, `enduser.id` (IAP email, when present, WP 13), `imposter.game.identity_mode`, `imposter.game.player_count`, `imposter.game.imposter_count`, `imposter.game.lineup` (models by seat), `imposter.game.category`, `imposter.game.word_sha256` (not the word in clear on the root, so traces lists do not spoil it), `imposter.game.outcome` (empty when aborted) |
| turn (`invoke_node play_turn`, the run of one seat) | `imposter.phase.name`, `imposter.phase.round` (0 for phases without rounds), `imposter.player.seat`, `imposter.player.name`, `imposter.player.role`, `gen_ai.request.model` (catalog id), `imposter.turn.attempts`, `imposter.turn.fallback` (bool), `imposter.turn.truncated` (bool) |
| `judge {kind}` | `imposter.judge.kind` (`guess`/`clue`), `imposter.judge.verdict`, `imposter.judge.confidence`, `imposter.judge.rationale` (with the probability of a model verdict), `gen_ai.request.model` (`code` for the code checks) |
| `decisions {model}` (client span) | `gen_ai.operation.name` (`decisions`), `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `server.address`, `http.response.status_code`, `imposter.decisions.question_count` |

Errors set span status `ERROR`: a turn with a player error or an invalid action (with the
exception recorded when the player raised), a failed call to the Decisions API, and the
root span of a game that was aborted or whose run stopped before the game was over. ADK records errors that escape a node on its own spans.

## Content capture

Content capture is **on** (demo data, nothing sensitive):

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY`: prompts and completions
  as Cloud Logging events, linked to the span by trace and span ID.
- `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`: keep large content out of span attributes
  (Cloud Trace attribute size limits).
- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.
- Our own structured responses (clue, statement, vote, private reasoning) are added as
  a span event on the turn span, named after the response type, with every field cut
  to 200 characters, so a trace is readable without opening logs.
- `setup_telemetry` (and `agent.py` for `adk web`) sets the three variables above as
  defaults, so values already in the environment win. The deployed service can set them
  in Terraform instead.

GCS completion upload (`OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`) and BigQuery
Agent Analytics are future work.

## Cost

Traces carry no cost or token totals of ours. Token usage is on ADK's `generate_content`
span of every model call, which is enough to see what a turn or a game used.
`telemetry/cost.py` computes cost from token usage and catalog prices for the CLI's
totals table, from the engine's `usage` events (from which the UI can show a running
total). Judge and word generator tokens are not counted there yet.

## Logging

Python `logging`, no `print`. The CLI keeps plain logs. App logs on Cloud Run (JSON with
`logging.googleapis.com/trace` and `logging.googleapis.com/spanId`, so they link to
traces) belong to the deployment work (WP 12). ADK's own prompt and completion logs
already carry the trace and span id.

## IAP identity

The API reads `X-Goog-Authenticated-User-Email` (format `accounts.google.com:user@org`),
strips the prefix and sets `enduser.id` on the root span. Locally the header is absent and
an optional `IMPOSTER_DEV_USER` setting is used instead. The header is trusted only because
IAP is the only ingress path (see `infrastructure.md`); validating the signed
`X-Goog-IAP-JWT-Assertion` header was left out in WP 13. A middleware stores the user in
a context variable for the length of the request, and the trace plugin sets `enduser.id`
on the root span when the run starts.

## Viewing

- Trace Explorer: filter by attribute `imposter.game.id`, or by
  `gen_ai.request.model` to compare models.
- The CLI prints the link of each game's trace at the end, and the UI links each game to
  its trace:
  `https://console.cloud.google.com/traces/explorer?project=<project>&tid=<trace id>`.
- Prompts and completions are in Logs Explorer, one entry per model call, with the
  prompt in the labels `gen_ai.system_instructions` and `gen_ai.input.messages` and the
  answer in `gen_ai.output.messages`. ADK's exporter writes the bare trace id into the
  `trace` field, not `projects/<project>/traces/<id>`, so Trace Explorer may not show the
  entries next to a span. Find them with this query instead, where `spanId` is the
  `generate_content` span of the call:
  `logName:"gen_ai.client.inference.operation.details" trace="<trace id>"`.
- Cloud Trace keeps traces 30 days, which serves as a free game archive.
