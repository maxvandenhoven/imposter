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
| Gemini | `gemini-3.1-pro-preview` | `global` only | not yet run |
| Gemini | `gemini-3.8-flash` | `global` | not yet run |
| Gemini | `gemini-3.5-flash-lite` | `global` | not yet run |
| Claude | `claude-sonnet-5-5` | `global` | not yet run |
| Claude | `claude-haiku-5-5` | `global` | not yet run |
| Open | `deepseek-ai/deepseek-v3.2-maas` | `global` | not yet run |
| Open | `qwen/qwen3-235b-a22b-instruct-2507-maas` | `global` | not yet run |
| Open | `openai/gpt-oss-120b-maas` | `global` | not yet run |
| Open | `meta/llama-4-maverick-17b-128e-instruct-maas` | `global` | not yet run |

## Catalog (`models/catalog.yaml`)

```yaml
- id: gemini-flash
  display_name: Gemini Flash
  provider: google            # google | anthropic | meta | qwen | deepseek | mistral
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
and word generation), Claude Sonnet, Claude Haiku, and 2–3 open models. `models/factory.py`
turns an entry into an ADK model object and `GenerateContentConfig`.
`GET /api/catalog` serves the catalog (without prices if preferred) to the setup screen.

## Identity

`identity_mode` decides how players are named in prompts and the public transcript:

| Mode | Names | What players learn |
|---|---|---|
| `seat` | Player 1 … Player N | Nothing about opponents |
| `names` (default) | Random neutral first names (Alice, Bob, Chen, Dara, ...) | Nothing about opponents |
| `models` | Model display names, numbered when repeated (`Claude Sonnet #2`) | Which model each opponent is |

The model behind each seat is always known to the UI; audience mode hides it until the
reveal, god mode shows it. The mode is recorded on the root span (`game.identity_mode`) so
traces can be filtered to compare behaviour.

## Words

- `words/categories/*.yaml`: built-in categories (animals, food, places, objects, jobs,
  sports, movies, nature, music, technology), 30–50 common words each.
- Modes: typed (with optional category), random from a category, generated.
- Generator: Gemini Flash-Lite with structured output `{word, category, hint}` and the
  list of recently used words (in memory) to avoid repeats. Traced as part of `setup`.
- Hint (when enabled): a related but non-revealing word for the imposter, generated at
  setup for typed and random words too.

## Judge

```python
class Judge(Protocol):
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
- `judge/llm_judge.py`: Gemini Flash-Lite with structured output. Temperature 0.
- Verdicts are events (`guess_judged`, and on the clue event) and span attributes.
- The Laya typed-decision model was considered: in Model Garden it is a self-deployed
  model (dedicated endpoint, billed per hour), which conflicts with scaling to zero. A
  `LayaJudge` on Cloud Run CPU is listed in `future-work.md`.
