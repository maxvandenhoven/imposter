# Models, words and judge

## Model access (Vertex AI only)

| Family | Access | ADK model |
|---|---|---|
| Gemini | Native Vertex AI | model id string, e.g. `gemini-<version>-flash` |
| Claude | Model Garden (partner model), enable in console first | `LiteLlm(model="vertex_ai/claude-...")` |
| Open models (Llama, Qwen, DeepSeek, Mistral, ...) | Vertex AI MaaS (serverless, pay per token), enable in console first | `LiteLlm(model="vertex_ai/<publisher>/<model>")` or the OpenAI-compatible MaaS endpoint, whichever the current docs recommend |

All calls go to location `global` unless the catalog entry sets `location` (some open
models are only served in specific regions such as `us-central1`). Authentication is ADC /
the service account; no API keys and no Secret Manager needed in v1.

Exact model IDs change often. WP 04 verifies them in Model Garden and with a test call per
model, and records them in the catalog. If the org sandbox blocks a model (org policy or
missing terms acceptance), drop it from the catalog.

### Verified model IDs

`scripts/check_models.py` sends one test call per candidate (location `global`, falling
back to `us-central1`). Candidates were picked from the Vertex AI and Anthropic model
lists in October 2026. Open MaaS model IDs carry the publisher prefix and the `-maas`
suffix; for LiteLLM all non-Gemini IDs get the `vertex_ai/` prefix. Update the *Result*
column after every run; WP 04 copies the working IDs into the catalog.

| Family | Model ID | Location | Result |
|---|---|---|---|
| Gemini | `gemini-3.1-pro-preview` | `global` only | OK (2026-10-29), in the catalog as `gemini-pro` |
| Gemini | `gemini-3.8-flash` | `global` | OK (2026-10-29), in the catalog as `gemini-flash` |
| Gemini | `gemini-3.5-flash-lite` | `global` | OK (2026-10-29), in the catalog as `gemini-flash-lite` |
| Claude | `claude-sonnet-5-5` | `global` | OK (2026-10-29), in the catalog as `claude-sonnet` |
| Claude | `claude-haiku-5-5` | `global` | OK (2026-10-29), in the catalog as `claude-haiku` |
| Open | `deepseek-ai/deepseek-v3.2-maas` | `global` | 404 (not enabled in the project), dropped |
| Open | `qwen/qwen3-235b-a22b-instruct-2507-maas` | `global` | 404 (not enabled in the project), dropped |
| Open | `openai/gpt-oss-120b-maas` | `global` | OK (2026-10-29), in the catalog as `gpt-oss` |
| Open | `mistral-small-2503` | `us-central1` only | OK (2026-11-01), in the catalog as `mistral-small` |
| Open | `deepseek-ai/deepseek-v4.1-flash-maas` | `global` | OK (2026-11-01), in the catalog as `deepseek-flash` |
| Open | `meta/llama-4-maverick-17b-128e-instruct-maas` | `global` | 404 (not enabled in the project), dropped |

Findings from WP 04, also noted in `catalog.yaml`:

- `gemini-3.8-flash` and `gemini-3.1-pro-preview` reject the minimal thinking level, so
  they cannot switch thinking off and run at `thinking: low`. Flash-Lite accepts it.
- LiteLLM implements structured output for Claude with a forced tool choice. Claude Haiku
  accepts it, Claude Sonnet rejects it, so Sonnet gets the JSON schema in the prompt.
  `gpt-oss` also uses JSON in the prompt.
- Claude Sonnet refuses (`content_filter`) when the game instruction is the system
  prompt, but answers when the same text is a user message. `AdkPlayer` therefore sends a
  short fixed system instruction (ADK `static_instruction`) and the rendered instruction
  as user content, for every model. Even so, in one of two full test games Sonnet
  refused a debrief turn (`SAFETY`), which fell back to an empty reflection. The same
  prompt with other game content passed every time, so the trigger is unclear. Sonnet is
  left out of the `slow` test until this is understood.
- Prices in the catalog are estimates from public price lists and third-party summaries
  in October 2026. Check them against the Vertex AI pricing page before relying on cost
  numbers.
- More open models need their terms accepted in Model Garden first. Add them to
  `scripts/check_models.py` and the catalog once they answer.

### Turn times and reasoning (WP 16)

`scripts/measure_models.py` plays random players up to a clue turn and the imposter's
guess, renders those real prompts and times a streamed answer per catalog model with the
settings the players use. Median total time of four runs, in seconds:

| Model | Clue | Guess | Note |
|---|---|---|---|
| `gemini-pro` | 6.7 | 8.4 | Thinks at `low`, 250 to 300 thinking tokens. |
| `gemini-flash` | 3.4 | 7.1 | Thinks at `low`. |
| `gemini-flash-lite` | 1.0 | 1.0 | No thinking. |
| `claude-sonnet` | 1.5 | 4.9 | No thinking. |
| `claude-haiku` | 1.2 | 2.9 | No thinking. |
| `mistral-small` | 1.3 | 1.4 | No thinking, slowest run 2.5 s. |
| `deepseek-flash` | 0.9 | 1.1 | No thinking, one 11 s stall in eight runs. |
| `gpt-oss` before | 21.1 (max 41.2) | not measured | Default reasoning effort, 60 s timeout. |
| `gpt-oss` after | 0.8 (max 1.7) | 2.7 (max 3.1) | `reasoning_effort: low`, 10 s timeout. |

Findings:

- Vertex MaaS honours `reasoning_effort` for `gpt-oss`: a clue turn went from 70 to 110
  thinking tokens to 20 to 35. A guess turn still thinks 280 to 520 tokens at `low`.
- Most of the slow turns were not caused by reasoning. `gpt-oss` on Vertex MaaS often
  stalls for 20 to 40 s before the first chunk or midway, whatever the answer length.
  The 60 s timeout never fired, so a stalled call took the whole stall, and a call that
  did time out was retried after another 60 s. LiteLLM models now have a 10 s limit
  (`LITELLM_CALL_TIMEOUT_SECONDS`), which for a stream is the wait for the first chunk
  and every pause between chunks, and a retry is usually fast again.
- LiteLLM retries only a call that fails before the first chunk. A stream that breaks
  off midway (`MidStreamFallbackError`) reached the runner as a failed turn, so
  `AdkPlayer` now asks again (`ANSWER_ATTEMPTS`, 3 calls).
- `gpt-oss` stalls the most, so the default lineup uses `mistral-small` as its open
  model instead (Gemini Flash, Claude Haiku, Mistral Small, Gemini Flash-Lite). A full
  default game with `make play` took about 63 s. `gpt-oss` stays in the catalog.

## Catalog (`models/catalog.yaml`)

```yaml
- id: gemini-flash
  display_name: Gemini Flash
  provider: google            # google | anthropic | openai | meta | qwen | deepseek | mistral
  adk_model: gemini-<version>-flash
  via: native                 # native | litellm
  location: global
  logo: logos/gemini.svg
  supports_structured_output: true
  thinking: off               # off | low | high (maps to thinking budget / extended thinking)
  temperature: 1.0
  price_per_mtok: {input: 0.0, output: 0.0}   # USD, from the pricing page, for estimates
```

Starting lineup: latest Gemini Pro, Gemini Flash, Gemini Flash-Lite (also used for judge
and word generation), Claude Sonnet, Claude Haiku, and the open models enabled in the
project (only `gpt-oss` so far). `models/factory.py` turns an entry into an ADK model
object (`Gemini` on Vertex AI or `LiteLlm`) and a `GenerateContentConfig` per phase:
temperature, `max_output_tokens` (a per-phase answer budget plus room for thinking) and
the thinking level. Models that always reason (`always_reasons: true`, `gpt-oss`) get
the setting as LiteLLM `reasoning_effort` (`off` and `low` become `low`, `high` stays
`high`), because they have no way to switch reasoning off.
`GET /catalog` serves the catalog to the setup screen (`web-ui.md` §API).

## Identity

`identity_mode` decides how players are named in prompts and the public transcript:

| Mode | Names | What players learn |
|---|---|---|
| `seat` | Player 1 … Player N | Nothing about opponents |
| `names` (default) | The classic names in alphabetical seat order (Alice, Bob, Charlie, Dave, ...) | Nothing about opponents |
| `models` | Model display names, numbered when repeated (`Claude Sonnet #2`) | Which model each opponent is |

The model behind each seat is always known to the UI; audience mode hides it until the
reveal, god mode shows it. The mode is recorded on the root span (`game.identity_mode`) so
traces can be filtered to compare behaviour.

## Words

- `words/categories/*.yaml`: built-in categories, 30–50 words each. Since playtest 1
  (`playtests.md`) they lean abstract and esoteric rather than concrete, so a single clue
  does not give the word away: for example emotions and moods, abstract concepts
  (justice, nostalgia), sensations and textures, sounds, rituals and customs,
  philosophical ideas, natural phenomena, crafts and techniques, historical eras, and
  idioms or figures of speech. A few concrete categories (animals, food, objects) stay
  for easy games.
- The category is hidden from every player by default (`public_category` off), and can
  be turned on per game.
- Modes: typed (with optional category), random from a category, generated.
- Generator: Gemini Flash-Lite with structured output `{word, category, hint}` and the
  list of recently used words (in memory) to avoid repeats. Traced as part of `setup`.
- Hint (when enabled): a related but non-revealing word for the imposter, generated at
  setup for typed and random words too.
- `words/options.py`: `WordOptions` (mode, typed word, category) are the setup choices,
  and `SecretWordResolver` turns them into a `SecretWord` before `Game.create`. A hint
  that mentions the word is rejected.
- Good secret words are familiar but many-sided, so civilians have room for clever clues
  that an imposter cannot easily decode. Obscure words are avoided.
- The generator and the LLM judge both run on `models/structured.py`
  (`StructuredTaskAgent`), an ADK `LlmAgent` with a response schema and a fresh session
  per task.

## Judge

```python
class JudgeProtocol(Protocol):
    async def is_same_word(self, guess: str, word: str) -> JudgeVerdict: ...
    async def is_valid_clue(self, clue: str, word: str) -> JudgeVerdict: ...

class JudgeVerdict(BaseModel):
    verdict: bool
    confidence: float  # 0..1
    rationale: str
    judge_model: str
```

- `judge/checks.py`: cheap code checks first (normalisation, exact match, substring /
  shared stem for clues). Only undecided cases reach the LLM.
- `judge/llm_judge.py`: `LlmJudge`, implementing `JudgeProtocol` with Gemini Flash-Lite and
  structured output. Temperature 0.
- `GameRunner` takes one `judge: JudgeProtocol` for both clues and guesses. The game
  setting `model_clue_check` (on by default) decides whether clues reach the model.
  When it is off, or no judge is set, only the code checks judge clues. When the
  model fails, the judge falls back to the lenient verdict (clue valid, guess wrong).
- Verdicts are on events (the `guess_made` event, and the rejection reason on the clue event)
  and span attributes.
- The Laya typed-decision model was considered: in Model Garden it is a self-deployed
  model (dedicated endpoint, billed per hour), which conflicts with scaling to zero. A
  `LayaJudge` on Cloud Run CPU is listed in `future-work.md`.
