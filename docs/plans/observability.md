# Observability

Goal: one game is one readable trace in Cloud Trace, filterable by model, role, phase and
identity mode, with full prompts and completions one click away in Cloud Logging.

## Setup

- ADK emits OpenTelemetry spans out of the box (`invocation` → `agent_run` → `call_llm` →
  `generate_content`, tools). Export uses ADK's own Google Cloud telemetry setup, the one
  behind `get_fast_api_app(otel_to_cloud=True)` (export over OTLP to
  `telemetry.googleapis.com`). Since we build our own FastAPI app, `telemetry/setup.py`
  calls the underlying setup function directly; check the installed ADK version for its
  name, and read the `google-agents-cli-observability` skill.
- LiteLLM calls (Claude, open models) must appear as spans too. Verify that ADK's
  `call_llm` span covers them; if model-level GenAI spans are missing, add the LiteLLM
  OpenTelemetry callback or a thin span in `AdkPlayer`.
- `telemetry/setup.py` is called once by both the CLI and the API.
- Exporter selection via settings: `cloud` (default when `GOOGLE_CLOUD_PROJECT` is set and
  ADC works), `console`, or `none` (tests).

## Span hierarchy

```
game                       (root, one per game)
├─ phase:setup             word pick/generation, role assignment
├─ phase:clue_1
│  ├─ turn                 one per player turn
│  │  └─ ADK invocation / agent_run / call_llm / generate_content
│  └─ ...
├─ phase:clue_2, discussion_1, discussion_2
├─ phase:vote              parallel turns
├─ phase:resolution
├─ phase:guess             turn + judge span
├─ phase:outcome
└─ phase:debrief           parallel turns
```

Attributes (prefix `imposter.` for our own, OTel semantic conventions where they exist):

| Span | Attributes |
|---|---|
| `game` | `imposter.game.id`, `enduser.id` (IAP email, when present), `imposter.game.identity_mode`, `imposter.game.player_count`, `imposter.game.imposter_count`, `imposter.game.lineup` (models by seat), `imposter.game.category`, `imposter.game.word_sha256` (not the word in clear on the root, so traces lists do not spoil it), `imposter.game.outcome`, `imposter.game.total_tokens`, `imposter.game.cost_usd` |
| `phase` | `imposter.phase.name`, `imposter.phase.round` |
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

- Trace Explorer: filter by span name `game` and attribute `imposter.game.id`, or by
  `gen_ai.request.model` to compare models.
- The UI links each game to its trace:
  `https://console.cloud.google.com/traces/explorer?project=<project>&tid=<trace id>`.
- Cloud Trace keeps traces 30 days, which serves as a free game archive.
