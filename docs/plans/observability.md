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
- `setup_telemetry` is called once by the CLI (and by the API, WP 08). It returns the
  project, which the CLI uses to print the Trace Explorer link of the game.
- Exporter selection via `IMPOSTER_TELEMETRY` or `imposter play --telemetry`: `cloud`
  (default when `GOOGLE_CLOUD_PROJECT` is set), `console` (spans to stderr), or `none`
  (tests, and the default without a project).

## Span hierarchy

The game runs as an ADK graph `Workflow` with a node per phase (`agents-and-orchestration.md`
§Game workflow), so ADK emits the game and phase levels of the trace itself. We add
attributes to those spans and open spans of our own only for turns and judge decisions,
which ADK has no span for. The hierarchy is pinned with fake players in
`tests/telemetry/test_spans.py`:

```
invoke_workflow game_runner                      game: one per game (ADK, attributes ours)
├─ invoke_node setup                             phase: one per phase and round (ADK)
├─ invoke_node clue                              clue round 1
│  ├─ turn {player name}                         one per player turn (ours)
│  │  ├─ invoke_workflow player_0_clue           the player's own ADK Runner (nested)
│  │  │  └─ invoke_agent player_0_clue
│  │  │     └─ generate_content {model}          tokens, finish reason
│  │  │        └─ POST                           one per HTTP attempt (aiohttp)
│  │  └─ judge clue                              one per judge decision (ours)
│  │     └─ invoke_workflow judge → invoke_agent judge → generate_content
│  └─ ...
├─ invoke_node clue                              clue round 2, the loop edge
├─ invoke_node discussion, discussion
├─ invoke_node vote                              parallel turns
├─ invoke_node resolution
├─ invoke_node guess                             turn, with a judge guess span inside
├─ invoke_node outcome
├─ invoke_node debrief                           parallel turns
└─ invoke_node done                              or invoke_node aborted
```

What ADK sets, as of ADK 2.13:

- `invoke_workflow game_runner` (the root under the Runner): `gen_ai.operation.name =
  invoke_workflow`, `gen_ai.conversation.id` (the session id, which is the game id) and
  `gen_ai.workflow.name`. It records the error when a node fails.
- `invoke_node {phase}`: `gen_ai.operation.name = invoke_node`, `gen_ai.conversation.id`
  and `gcp.vertex.agent.associated_event_ids` (the ADK events the node run yielded). A
  node runs once per phase and round, so the clue and discussion rounds are separate
  spans with the same name.
- Each `AdkPlayer` and the judge run their own ADK `Runner`, which opens a nested
  `invoke_workflow {agent}` span (`gen_ai.workflow.nested = true`) around `invoke_agent
  {agent}` and `generate_content {model}`. The latter carries `gen_ai.request.model`,
  `gen_ai.request.max_tokens`, `gen_ai.agent.name`, `gen_ai.usage.input_tokens` and
  `gen_ai.usage.output_tokens`, also for LiteLLM models (Claude, `gpt-oss`).

How our attributes and spans get there (`telemetry/spans.py`):

- **Game.** A node cannot reach the root span, but ADK runs the run callbacks of plugins
  inside it. `GameTracePlugin`, an ADK `BasePlugin` registered on the `App` (in
  `run_game` and in `agent.py` for `adk web`), notes the trace id before the run and sets
  the game attributes after it (or in `on_run_error_callback`), from the game in the
  store. This keeps ADK's span as the root instead of adding a `game` span above it.
- **Phase.** The `invoke_node` span is the current span inside a node, so
  `GamePhaseNode` calls `mark_phase` on it.
- **Turn.** `GameRunner.ask` opens `turn {player name}` (`turn_span`) around the player's
  attempts and the judge calls of the turn. ADK has no span per turn: each attempt opens
  its own nested `invoke_workflow`, and the retry and the fallback only exist at this
  level. The tokens are not repeated on the turn: ADK sets
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` and
  `gen_ai.usage.reasoning.output_tokens` on every `generate_content` span, and the
  same numbers are in its log entry of the call.
- **Judge.** `LlmJudge` opens `judge {kind}` (`judge_span`) around each decision. Most
  decisions are made by the code checks, which ADK does not see, and ADK's spans of the
  model call do not carry the verdict.

Trace Explorer filters use `imposter.*` attributes rather than span names, because the
ADK names repeat.

Attributes (prefix `imposter.` for our own, OTel semantic conventions where they exist):

| Span | Attributes |
|---|---|
| game (`invoke_workflow game_runner`) | `imposter.game.id`, `enduser.id` (IAP email, when present, WP 13), `imposter.game.identity_mode`, `imposter.game.player_count`, `imposter.game.imposter_count`, `imposter.game.lineup` (models by seat), `imposter.game.category`, `imposter.game.word_sha256` (not the word in clear on the root, so traces lists do not spoil it), `imposter.game.outcome` (empty when aborted) |
| phase (`invoke_node {phase}`) | `imposter.phase.name`, `imposter.phase.round` (phases with rounds) |
| `turn {player name}` | `imposter.phase.name`, `imposter.player.seat`, `imposter.player.name`, `imposter.player.role`, `gen_ai.request.model` (catalog id), `imposter.turn.attempts`, `imposter.turn.fallback` (bool), `imposter.turn.truncated` (bool) |
| `judge {kind}` | `imposter.judge.kind` (`guess`/`clue`), `imposter.judge.verdict`, `imposter.judge.confidence`, `gen_ai.request.model` (`code` for the code checks) |

Errors set span status `ERROR`: a turn with a player error or an invalid action (with the
exception recorded when the player raised), and the root span of an aborted game, with
the abort reason. ADK records errors that escape a node on its own spans.

## Content capture

Content capture is **on** (demo data, nothing sensitive):

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY`: prompts and completions
  as Cloud Logging events, linked to the span by trace and span ID.
- `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`: keep large content out of span attributes
  (Cloud Trace attribute size limits).
- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.
- Our own structured responses (clue, statement, vote, private reasoning) are added as
  a span event on the `turn` span, named after the response type, with every field cut
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
`X-Goog-IAP-JWT-Assertion` header is a nice extra in WP 13.

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
