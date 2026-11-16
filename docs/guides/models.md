# Adding or changing a model

This guide adds a model to the catalog so it can play a seat, and records what is known
about the models that are in it. It assumes the project setup of
[`gcp-setup.md`](gcp-setup.md).

## How models are reached

Every player model runs on Vertex AI in the project, so there is one bill and one set of
quotas, and no API keys.

| Family | Access | In the catalog |
|---|---|---|
| Gemini | Native Vertex AI | `via: native`, with the model ID as `adk_model` |
| Claude | Model Garden partner model, enabled in the console first | `via: litellm`, with `vertex_ai/claude-...` |
| Open models | Vertex AI model as a service, enabled in the console first | `via: litellm`, with `vertex_ai/<publisher>/<model>` |

Calls go to the location `global` unless the catalog entry sets another one, because
some open models are served only in a region such as `us-central1`.

## Procedure

1. Enable the model in Model Garden, which accepts its terms for the project. There is
   no API for this step.
2. Add the model ID to the candidates in `scripts/check_models.py` and send a test call.

   ```
   uv run --env-file .env python scripts/check_models.py
   ```

   The script prints `OK` or the error per model, trying `global` and then
   `us-central1`.
3. Add an entry to `src/imposter/models/catalog.yaml` with the fields below. Take the
   prices from the Vertex AI pricing page.
4. Add a logo to `frontend/public/logos/` when the provider has none yet.
5. Time a turn, and adjust the entry when the model is slow or reasons by default.

   ```
   uv run --env-file .env python scripts/measure_models.py --model <id>
   ```

6. Play a game with the model in the imposter seat, which acts in every phase, by adding
   its ID to the parameters of `tests/players/test_llm_player_slow.py` and running
   `make test-slow`.

## Catalog fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | The ID used in game requests, `-p` options and usage events. |
| `display_name` | string | yes | The name shown in the web app, and the player name in the `models` identity mode. |
| `provider` | enum | yes | The publisher of the model, such as `google` or `anthropic`. |
| `adk_model` | string | yes | The model ID for Gemini, or the LiteLLM model string with the `vertex_ai/` prefix. |
| `via` | `native` or `litellm` | yes | `native` builds ADK's `Gemini` model, and `litellm` builds `LiteLlm`. |
| `location` | string | no | The Vertex AI location, `global` by default. |
| `logo` | path | no | A path below `frontend/public/`, such as `logos/gemini.svg`. |
| `supports_structured_output` | bool | no | It is false by default. When false, the response schema is left out of the request and the task asks for JSON. |
| `thinking` | `off`, `low` or `high` | no | The native thinking level. Thinking tokens count against the budget of a game. |
| `always_reasons` | bool | no | For models that cannot switch reasoning off. The thinking setting is then sent as LiteLLM's `reasoning_effort`. |
| `temperature` | number | no | The default sampling temperature, which a game can override. |
| `price_per_mtok` | `{input, output}` | yes | USD per million tokens, used only for cost estimates. |

`GET /catalog` serves the catalog to the setup screen. The prices are estimates that
someone typed in, so check them before you rely on a cost number.

## What is known about the models

These findings are also noted in the catalog file. They were measured in October and
November 2026.

| Model | Finding |
|---|---|
| Gemini Pro and Flash | They reject the minimal thinking level, so they cannot switch thinking off and run at `thinking: low`. Flash-Lite accepts it. |
| Claude Sonnet | LiteLLM implements structured output for Claude with a forced tool choice, which Sonnet rejects, so it gets the JSON schema in the prompt. It also refuses the game instruction as a system prompt and answers when the same text is a user message. It still refused one debrief turn in testing, for a reason that is not understood, so it is left out of the slow tests. |
| Claude Haiku | It accepts LiteLLM's structured output. |
| `gpt-oss` | It always reasons, so `off` is sent as the lowest `reasoning_effort`. On Vertex AI it often stalls for 20 to 40 seconds before the first chunk or midway. |
| `mistral-small` | It is served only in `us-central1`. It is the open model of the default lineup, because it stalls least. |
| `deepseek-flash` | It is fast, with an occasional stall of about 10 seconds. |

Stalls are why calls through LiteLLM have a limit of 10 seconds, which for a stream is
the wait for the first chunk and every pause between chunks, with two retries. LiteLLM
retries only a call that fails before the first chunk, so ADK retries the agent when a
stream breaks off midway (`ANSWER_RETRY` in `players/llm_player.py`). A full default
game takes about a minute.

Median time of a turn in seconds, from `scripts/measure_models.py` with four runs each:

| Model | Clue | Guess |
|---|---|---|
| `gemini-pro` | 6.7 | 8.4 |
| `gemini-flash` | 3.4 | 7.1 |
| `gemini-flash-lite` | 1.0 | 1.0 |
| `claude-sonnet` | 1.5 | 4.9 |
| `claude-haiku` | 1.2 | 2.9 |
| `mistral-small` | 1.3 | 1.4 |
| `deepseek-flash` | 0.9 | 1.1 |
| `gpt-oss` | 0.8 | 2.7 |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `404 ... not found` or `Publisher model ... not found` | The model ID is wrong, the model is not served in that location, or it is not enabled in Model Garden. |
| `403 ... terms of service` or `not allowlisted` | The model is not enabled in Model Garden, or an org policy blocks it. |
| `429 Resource exhausted` | The quota of the model is too low. Request an increase on the Quotas page. |
| Every turn of the model falls back with a `ValidationError` | The model does not follow the response schema. Set `supports_structured_output: false`. |
| A run fails with a `KeyError` in the first turn | The request names a model ID that is not in the catalog. The CLI and the setup screen only offer catalog models. |
