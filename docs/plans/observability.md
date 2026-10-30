# Observability

Goal: one game is one readable trace in Cloud Trace, filterable by model, role, phase and
identity mode, with full prompts and completions one click away in Cloud Logging.

## Setup

- ADK emits OpenTelemetry spans out of the box (`invoke_workflow`, `invoke_node`,
  `invoke_agent`, `generate_content` and tools, see §Span hierarchy). Export uses ADK's own Google Cloud telemetry setup, the one
  behind `get_fast_api_app(otel_to_cloud=True)` (export over OTLP to
  `telemetry.googleapis.com`). Since we build our own FastAPI app, `telemetry/setup.py`
  calls the underlying setup function directly; check the installed ADK version for its
  name, and read the `google-agents-cli-observability` skill.
- LiteLLM calls (Claude, open models) appear as spans too: ADK's `generate_content`
  span covers them, with token usage (checked in a real game in `adk web`).
- `telemetry/setup.py` is called once by both the CLI and the API.
- Exporter selection via settings: `cloud` (default when `GOOGLE_CLOUD_PROJECT` is set and
  ADC works), `console`, or `none` (tests).

## Span hierarchy

The game runs as an ADK graph `Workflow` with a node per phase (`agents-and-orchestration.md`
§Game workflow), so ADK emits the game and phase levels of the trace itself. These are
the spans of a real game, read from `adk web` (the fake-player version is pinned in
`tests/orchestration/test_runner_workflow.py`):

```
invoke_workflow game_runner                      game: one per game (ADK)
├─ invoke_node setup                             phase: one per phase and round (ADK)
├─ invoke_node clue                              clue round 1
│  ├─ (turn)                                     one per player turn (ours, planned)
│  │  └─ invoke_workflow player_0_clue           the player's own ADK Runner (nested)
│  │     └─ invoke_agent player_0_clue
│  │        └─ generate_content {model}          tokens, finish reason
│  ├─ invoke_workflow judge → invoke_agent judge → generate_content
│  └─ ...
├─ invoke_node clue                              clue round 2, the loop edge
├─ invoke_node discussion, discussion
├─ invoke_node vote                              parallel turns
├─ invoke_node resolution
├─ invoke_node guess                             turn + judge span
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

So the tracing work does not need `phase` spans of its own. The `invoke_node` span is the
current span inside a node, so the phase attributes go on it directly, and a `turn` span
per player turn in `GameRunner.ask` then parents the player's nested `invoke_workflow`.
The `invoke_workflow game_runner` span is not reachable from a node, so the game
attributes need one of three ways, to be chosen in the tracing work: an ADK plugin
callback that sees the workflow span, a span processor that copies the attributes from
the setup node's span, or a `game` span of our own around `runner.run_async` in
`run_game`, which would then be the root above `invoke_workflow`. Trace Explorer filters
use `imposter.*` attributes rather than span names, because the ADK names repeat.

Attributes (prefix `imposter.` for our own, OTel semantic conventions where they exist):

| Span | Attributes |
|---|---|
| `game` (`invoke_workflow game_runner`) | `imposter.game.id`, `enduser.id` (IAP email, when present), `imposter.game.identity_mode`, `imposter.game.player_count`, `imposter.game.imposter_count`, `imposter.game.lineup` (models by seat), `imposter.game.category`, `imposter.game.word_sha256` (not the word in clear on the root, so traces lists do not spoil it), `imposter.game.outcome`, `imposter.game.total_tokens`, `imposter.game.cost_usd` |
| `phase` (`invoke_node {phase}`) | `imposter.phase.name`, `imposter.phase.round` |
| `turn` | `imposter.player.seat`, `imposter.player.name`, `imposter.player.role`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `imposter.usage.thinking_tokens`, `imposter.cost_usd`, `imposter.turn.attempts`, `imposter.turn.fallback` (bool), `imposter.turn.truncated` (bool) |
| judge | `imposter.judge.kind` (`guess`/`clue`), `imposter.judge.verdict`, `imposter.judge.confidence`, `gen_ai.request.model` |

Errors (`player_error`, aborts) set span status `ERROR` with the exception recorded.

## Content capture

Content capture is **on** (demo data, nothing sensitive):

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY`: prompts and completions
  as Cloud Logging events, linked to the span by trace and span ID.
- `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`: keep large content out of span attributes
  (Cloud Trace attribute size limits).
- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.
- Our own structured responses (clue, statement, vote, private reasoning) are added as
  span events on the `turn` span, small and truncated, so a trace is readable without
  opening logs.

GCS completion upload (`OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`) and BigQuery
Agent Analytics are future work.

## Cost

`telemetry/cost.py` computes cost from token usage and catalog prices. Per turn it goes on
the span and into a `usage` event (the UI shows a running total); per game on the root.

## Logging

Python `logging` with a JSON formatter on Cloud Run (structured logs with
`logging.googleapis.com/trace` so app logs are linked to traces). No `print`.

## IAP identity

The API reads `X-Goog-Authenticated-User-Email` (format `accounts.google.com:user@org`),
strips the prefix and sets `enduser.id` on the root span. Locally the header is absent and
an optional `IMPOSTER_DEV_USER` setting is used instead. The header is trusted only because
IAP is the only ingress path (see `infrastructure.md`); validating the signed
`X-Goog-IAP-JWT-Assertion` header is a nice extra in WP 13.

## Viewing

- Trace Explorer: filter by attribute `imposter.game.id`, or by
  `gen_ai.request.model` to compare models.
- The UI links each game to its trace:
  `https://console.cloud.google.com/traces/explorer?project=<project>&tid=<trace id>`.
- Cloud Trace keeps traces 30 days, which serves as a free game archive.
