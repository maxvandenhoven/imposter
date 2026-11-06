# Evaluation

How the prompts of the judge and the players are measured with ADK's eval framework, and
the log of every prompt change made because of an eval. WP 17 (#29) built it. Decision
D33 in `README.md` explains why the evals use ADK's own primitives.

## What is evaluated

A case is one model call in a fixed situation from a real game: the judge deciding one
clue, or one player taking one turn. Cases are cheap, repeatable and independent of the
rest of a game. Whether whole games get better (who wins, how often the imposter guesses
the word) is the tournament's job (WP 14).

The evals cover the problems seen in played games:

| Problem seen in games | Eval set | Metric |
|---|---|---|
| The judge rejects fair clues | `judge_clue/clue_labels` | `verdict_match` against hand-made labels |
| Players say the secret word | `player_clue/*`, `player_discussion/*`, and the `word_said` hard cases | `word_kept_secret` |
| Clues break the rules or are rejected, so turns are retried | `player_clue/civilian`, `player_clue/imposter` | `clue_follows_rules`, `clue_passes_judge` |
| Clues are synonyms of the word | `player_clue/civilian` | the not-a-synonym rubric |
| Clues make the word easy to guess, so a caught imposter still wins | `player_clue/civilian` | `clue_keeps_word_hidden` |
| Imposter clues give the imposter away | `player_clue/imposter` | the blends-in rubric |
| Statements misquote the game | `player_discussion/statement` | the grounded rubric |
| Private reasoning, statements and debriefs are too long | `player_clue/*`, `player_discussion/statement`, `player_debrief/reflection` | `within_word_caps`, `reflection_brief` |
| Debriefs are vague or invent things | `player_debrief/reflection` | the specific-and-faithful rubric |

Votes and the imposter's guess have no eval set yet: no problems were seen in them, and
the guess mostly measures how much the clues gave away, which `clue_keeps_word_hidden`
measures more directly.

## Layout

Everything lives in `evals/`, outside the package, because it is development tooling and
`adk eval` loads agents by folder.

| Path | What it is |
|---|---|
| `evals/judge_clue/` | The ADK app of the clue judge. `agent.py` exposes the production judge's `LlmAgent` as `root_agent`, unchanged. |
| `evals/player_clue/`, `evals/player_discussion/`, `evals/player_debrief/` | The ADK apps of a player turn in each phase. `agent.py` exposes `player_eval_agent(phase)` from `evals/player_turn.py`: a `clone()` of the production agent of that phase of `AdkPlayer`, which renders its instruction and task from the `PlayerView` in the session state of the case, with the production templates. The model comes from `IMPOSTER_EVAL_MODEL`. |
| `evals/<app>/<name>[_dev\|_holdout].evalset.json` | The eval sets, in ADK's format. |
| `evals/<app>/<name>.test_config.json` | The `EvalConfig` of each eval set: the metrics, their thresholds and the grader model. |
| `evals/imposter_metrics.py` | The custom metrics, imported by ADK by name. They reuse the game's own rules and, for `clue_passes_judge`, the production judge. |
| `evals/player_turn.py` | The player eval agents, and `case_view`, which plays every case with the current default word caps of `GameConfig`. |
| `evals/data/clue_labels.yaml` | Hand-made labels of every clue proposed in the exported games, plus a few hand-made forms of the word that the code checks miss. |
| `evals/raw/<day>/` | Exports of Cloud Logging and Cloud Trace (git-ignored): `logs.jsonl` with every model call and its prompt and answer, and `traces/` with the game traces. |
| `scripts/harvest_traces.py` | Exports the logs and traces of played games to `evals/raw/<today>/`. |
| `scripts/build_evalsets.py` | Builds the label candidates and the eval sets from the exports and the labels. |
| `scripts/eval_report.py` | Summarises and compares runs from `evals/<app>/.adk/eval_history/`, which `adk eval` writes. |

## Data

The cases come from real games. ADK logs every model call to Cloud Logging with its full
prompt and answer, linked to the trace of the game (`observability.md`). Cloud Logging
keeps them 30 days, so `make eval-harvest` exports them to `evals/raw/`. The traces of
games played on Cloud Run are currently missing from Cloud Trace (#36), but the logs are
complete, and the eval sets only need the logs.

- **Judge cases.** `build_evalsets.py labels` collects every (secret word, clue) pair
  proposed by a player or sent to the judge and appends the new ones to
  `clue_labels.yaml` without a label. A person then labels each pair: `legal` (only forms
  of the word are illegal, see `game-rules.md` §Validation) and `synonym` (legal, but a
  weak clue). The judge eval set holds the labelled pairs that the code checks leave to
  the model, with the label as the expected answer. A unit test checks that the code
  checks agree with every label.
- **Player cases.** `build_evalsets.py players` parses the `PlayerView` of every
  first-attempt clue, discussion and debrief turn back from its logged prompt, and keeps
  it only when rendering it again with the current templates gives exactly the logged
  prompt, so a parse error cannot slip in. The view goes into the session state of the
  case, so the case stays valid when a template changes. Each eval set is split by secret
  word into a development set (about 70%) and a holdout set that is only graded at the
  end of a change, to catch prompts fitted to the cases they were tuned on.
- **Hard cases.** Saying the word is rare per call (1 to 7% of turns), so a normal eval
  set barely shows it. The `word_said` eval sets hold the turns whose logged answer said
  the word, each repeated 5 times, so a prompt change that fixes or keeps them shows up.
  They are selected by an earlier failure, so their pass rate is a worst case, not a
  rate to expect in games.

The 2026-11-04 export holds 50 games and gives:

| Eval set | Development | Holdout |
|---|---|---|
| `judge_clue/clue_labels` | 296 (not split) | |
| `player_clue/civilian` | 168 | 75 |
| `player_clue/imposter` | 56 | 26 |
| `player_clue/word_said` | 40 (8 turns, 5 times) | |
| `player_discussion/statement` | 156 | 59 |
| `player_discussion/word_said` | 25 (5 turns, 5 times) | |
| `player_debrief/reflection` | 110 | 48 |

## Metrics

| Metric | Kind | What it checks |
|---|---|---|
| `verdict_match` | custom, code | The judge's verdict equals the label. Reported per kind of clue: legal, synonym (legal) and illegal. |
| `clue_follows_rules` | custom, code | The clue is one word, was not given before and does not say the word, by the engine's own checks. It does not ask the judge. |
| `clue_passes_judge` | custom, production judge | The production judge (its code checks, then its model) accepts the clue. A failure costs a retry in a game, or a pass for an imposter. |
| `word_kept_secret` | custom, code | The clue or statement does not say the secret word, by the engine's rules (`Game.clue_says_word`, `Game.statement_says_word`). A failure ends a game and loses it for the speaker's side. |
| `clue_keeps_word_hidden` | custom, guesser model | A fixed guesser (Gemini Flash, temperature 0) makes three guesses from the clues so far, with and without the new clue. The clue fails when the word is among the guesses only with it. |
| `within_word_caps` | custom, code | The statement and the private reasoning keep to the word caps of the prompt. The game cuts longer texts, so this measures whether the player follows the prompt. |
| `reflection_brief` | custom, code | The debrief reflection has at most 80 words (`DEBRIEF_WORD_TARGET`). |
| `rubric_based_final_response_quality_v1` | built-in, LLM | Gemini Flash grades one rubric per eval set, 3 samples per case: not a synonym (civilian clues), blends in (imposter clues), grounded in the game (statements), specific and faithful (debriefs). The rubric texts are in `QUALITY_RUBRICS` of `build_evalsets.py`. |

ADK passes a custom metric only the invocations of a case, not its session state. A
player case therefore carries its view and its secret word a second time, as rubrics of
the types `PLAYER_VIEW` and `SECRET_WORD`, which no built-in metric grades and ADK copies
onto every invocation. The user message of a player case is the full rendered prompt, so
the rubric grader sees the game. The eval agent does not send it: it renders the prompts
again from the view.

## Judge improvements versus player improvements

The judge and the players affect each other: a stricter judge rejects more clues, and a
player that gives worse clues gets more of them rejected. The evals keep the two apart in
three ways.

1. **The judge has its own eval with fixed inputs.** `judge_clue` grades the judge on
   labelled clues, without any player. A judge change is measured there first.
2. **Player metrics name what they depend on.** `clue_follows_rules`, `word_kept_secret`,
   the length metrics and the rubrics depend on the player only, and are graded by code or
   by fixed grader models that are not part of the game. Only `clue_passes_judge` asks the
   production judge. When `clue_passes_judge` moves but `clue_follows_rules` and the judge
   eval do not, the players changed what kind of clue they give. When the judge eval
   moves, `clue_passes_judge` moves with it, even with the same players.
3. **One side changes at a time, and baselines follow the judge.** A prompt change touches
   either the judge or a player prompt, never both. After a judge change, the player
   baselines of `clue_passes_judge` are run again before a player change is compared to
   them. Every entry of the change log names the judge version it was measured with.

The graders themselves (the rubric model and the guesser) stay fixed. Changing them is a
separate experiment that needs a new baseline of everything.

## Running

```
make eval-harvest   # export the logs and traces of the last games (ADC)
make eval-sets      # add new clues to the labels, rebuild all eval sets
make eval-judge     # grade the judge on the labelled clues
make eval-players   # grade every player eval set for each model in EVAL_MODELS
make eval-summary   # the latest run of every eval set and model
make eval           # all of the above except harvest and sets
make eval-players EVAL_SUITES=player_clue/civilian EVAL_MODELS=gemini-flash
make eval-players EVAL_SPLIT=holdout
make eval-compare APP=player_clue BASE=<run id> NEW=<run id>
```

`uv run python scripts/eval_report.py list player_clue` lists the run ids, and
`summary --markdown` prints the tables of this page. The runs and the log of each run are
in `evals/<app>/.adk/` (git-ignored). The models of the default lineup can run in parallel, one `make
eval-players EVAL_MODELS=<model>` each. Evals make real model calls and are never part of
`make test`. A full run of all player eval sets takes about an hour per model, mostly for
the rubric grader.

## Results

### Judge

| Judge version | Legal, not synonym (236) | Synonym (48) | Illegal (12) | All (296) |
|---|---|---|---|---|
| 0, synonyms invalid | 216 (92%) | 8 (17%) | 12 (100%) | 236 (80%) |
| 1, synonyms valid | 235 (100%) | 46 (96%) | 12 (100%) | 293 (99%) |

### Players

All runs are single runs at each model's default temperature. Repeating one eval set
three times (Claude Haiku, imposter clues, 56 cases) gave pass rates within 2 cases of
each other, so differences of one or two cases are noise. Each cell shows the baseline
(the prompts of 2026-11-05 with judge version 1) and the result after the player changes
2 to 5, on the development sets.

**Civilian clues** (168 cases):

| Model | Follows rules | Passes judge | Word kept secret | Keeps word hidden | Within caps | Not a synonym |
|---|---|---|---|---|---|---|
| Gemini Flash | 100 → 100 | 98 → 98 | 100 → 100 | 73 → 76 | 100 → 100 | 82 → 98 |
| Gemini Flash-Lite | 100 → 100 | 98 → 97 | 100 → 100 | 77 → 78 | 100 → 100 | 74 → 89 |
| Claude Haiku | 98 → 99 | 90 → 94 | 98 → 99 | 77 → 82 | 97 → 96 | 81 → 84 |
| Mistral Small | 100 → 100 | 98 → 100 | 100 → 100 | 76 → 81 | 100 → 100 | 80 → 85 |

**Imposter clues** (56 cases) and the clue hard cases (`word_said`, 40 cases):

| Model | Follows rules | Passes judge | Word kept secret | Blends in | Hard cases: word kept secret |
|---|---|---|---|---|---|
| Gemini Flash | 93 → 100 | 88 → 96 | 93 → 100 | 73 → 73 | 92 → 100 |
| Gemini Flash-Lite | 86 → 89 | 77 → 84 | 86 → 89 | 59 → 57 | 72 → 62 |
| Claude Haiku | 84 → 77 | 79 → 68 | 84 → 77 | 58 → 64 | 18 → 35 |
| Mistral Small | 86 → 86 | 79 → 82 | 86 → 86 | 57 → 59 | 72 → 70 |

**Discussion statements** (156 cases) and the statement hard cases (`word_said`, 25
cases):

| Model | Word kept secret | Within caps | Grounded | Hard cases: word kept secret |
|---|---|---|---|---|
| Gemini Flash | 99 → 99 | 99 → 100 | 99 → 99 | 88 → 96 |
| Gemini Flash-Lite | 94 → 97 | 100 → 100 | 92 → 93 | 64 → 76 |
| Claude Haiku | 95 → 99 | 72 → 97 | 90 → 94 | 64 → 76 |
| Mistral Small | 92 → 98 | 100 → 100 | 88 → 86 | 84 → 84 |

**Debrief reflections** (110 cases):

| Model | At most 80 words | Specific and faithful | Median words |
|---|---|---|---|
| Gemini Flash | 0 → 100 | 99 → 99 | 140 → 70 |
| Gemini Flash-Lite | 0 → 100 | 85 → 85 | 130 → 62 |
| Claude Haiku | 0 → 25 | 77 → 80 | 192 → 87 |
| Mistral Small | 0 → 100 | 67 → 62 | 128 → 49 |

The median private reasoning fell from 29 to 37 words to 19 to 35 words in clue turns, and
from 34 to 44 words to 23 to 37 words in discussion turns.

**Holdout sets**, graded once with the final prompts:

| Eval set | Gemini Flash | Gemini Flash-Lite | Claude Haiku | Mistral Small |
|---|---|---|---|---|
| Civilian clues (75): not a synonym | 96 | 75 | 71 | 85 |
| Civilian clues: keeps word hidden | 73 | 79 | 76 | 79 |
| Imposter clues (26): word kept secret | 100 | 88 | 88 | 92 |
| Statements (59): word kept secret | 98 | 97 | 97 | 100 |
| Debriefs (48): at most 80 words | 100 | 100 | 23 | 100 |

The holdout sets agree with the development sets for Gemini Flash and Mistral Small. The
synonym rate of Gemini Flash-Lite and Claude Haiku is worse on the holdout words (75% and
71% against 89% and 84%), which hints that the synonym guidance helps less on some words
than the development set suggests.

**A real game** with the default lineup after the changes (`make play`, seed 11, secret
word `bell`) ended in clue round 1. The civilians gave `bronze`, `ringing` and `church`,
each accepted at the first attempt, and then the imposter (Gemini Flash-Lite) gave `bell`
and lost at once. In the exported games before the changes, a game with two clue rounds
had 4.2 retried clue turns on average (31% of the clue calls). The game had no retries,
but it was too short to compare, and it shows the open problem of imposters saying the
word (§Next). The debriefs were 60 to 75 words long.

## Prompt change log

Every prompt change made because of an eval, oldest first, with the scores before and
after. Scores are pass rates on the development sets unless noted.

### Change 1: the judge allows synonyms (judge version 1, 2026-11-05)

- **Prompt:** `VALID_CLUE_TASK` in `judge/llm_judge.py`. Before: a clue is invalid when it
  is "a trivial derivative of the secret word: another form of it, a compound or word
  that contains it, a direct synonym, or a translation". After: a clue is invalid only
  when it is a form of the word itself (another grammatical form, a word that contains it
  or is contained in it, a translation), and every other clue is valid, "however close
  or obvious".
- **Why:** in the exported games the judge rejected 37% of the clues it saw. Besides
  synonyms it rejected fair associations such as `keeper` and `beacon` for lighthouse,
  `clove` for garlic, `cured` for charcuterie and `diploma` for graduation, and players
  often resubmitted the same rejected clue. The owner decided that synonyms are legal
  but discouraged in the player prompts, because frequent rejections make games slow
  and frustrating.
- **Result:** see §Judge. Wrong rejections of legal non-synonyms fell from 20 to 1, and
  all 12 illegal forms are still rejected. The remaining misses are `cured` for
  charcuterie, `thankfulness` for gratitude and `muddled` for befuddled. The judge
  instruction (`JUDGE_INSTRUCTION`) is unchanged, because the guess task shares it.

### Change 2: imposters must not give the obvious word (2026-11-06, judge version 1)

- **Prompt:** `role_imposter.md` now says that the imposter's best guess is most likely the
  secret word itself and must be treated as forbidden. `phase_clue.md` adds, for imposters
  only, that the most obvious word that fits all the clues is most likely the secret word,
  "even when it feels like a safe, general word", and asks for a word one step away from
  it instead.
- **Why:** 7% of the imposter clues in the exported games said the word, more than any
  other kind of turn. The reasoning of the models showed why: they gave the word that ties
  the clues together because it seemed "a safe, generic related word", for example
  "The secret word is almost certainly Clock or Watch. I will use Clock to blend in".
- **Result:** Gemini Flash no longer says the word (93% to 100%, hard cases 92% to 100%).
  For the other models the effect is small or mixed. Claude Haiku keeps the word secret
  in fewer development cases: three runs with the old wording gave 47, 45 and 45 of 56,
  three with the new wording 43, 43 and 44, while its hard cases rose from 18% to 35%.
  The change was kept for its effect on Gemini Flash, and the imposter problem stays the
  main open point (§Next).

### Change 3: civilians avoid synonyms (2026-11-06, judge version 1)

- **Prompt:** `role_civilian.md` now describes a good clue (something only a player who
  knows the word would connect to it, such as a part, a place, a use, a detail or a
  memory, that does not point to the word on its own) and forbids synonyms, "synonyms
  seem safe, but they hand the word to the imposter".
- **Why:** with synonyms legal since change 1, the players still need to avoid them. The
  baseline graded 18 to 26% of civilian clues as synonyms, and the models' reasoning
  called them safe ("Envy is a very close synonym and a strong, safe first clue").
- **Result:** fewer synonyms for every model (for example Gemini Flash 82% to 98% not a
  synonym), and the word is a little harder to guess from the clues (`clue_keeps_word_hidden`
  up 1 to 5 points). More clues pass the judge for Claude Haiku (90% to 94%).

### Change 4: shorter debriefs and reasoning (2026-11-06, judge version 1)

- **Prompt:** `phase_debrief.md` asks for three or four short sentences, at most 80 words,
  instead of "about 150 words". Every task with private reasoning (`phase_clue.md`,
  `phase_discussion.md`, `phase_vote.md`, `phase_guess.md`) asks for it "in one or two
  short sentences".
- **Why:** the owner found the debriefs and the private reasoning too long. The word cap of
  the reasoning stayed at 60, so the game options did not change.
- **Result:** debriefs are about half as long, and within 80 words for three of the four
  models. Claude Haiku halved its debriefs too but stays above 80 words in most cases. The
  reasoning is 15 to 35% shorter. The first version of this change asked only for "at most
  80 words" in the debrief. Claude Haiku ignored it (0% within 80 words), which led to the
  wording with sentences.

### Change 5: statements talk about "the word" (2026-11-06, judge version 1)

- **Prompt:** `phase_discussion.md` asks to keep statements short, to talk about the secret
  word without naming it or the word one thinks it is, calling it "the word", and warns
  that naming it "even to explain a clue" loses the game.
- **Why:** 2 to 4% of the statements in the exported games said the word, most often a
  civilian explaining their own clue ("keeping a gratitude journal"), and Claude Haiku
  wrote statements over the 100-word cap in 28% of the cases.
- **Result:** statements say the word less for every model (for example Mistral Small 92%
  to 98% and Claude Haiku 95% to 99% kept secret), the hard cases improved by 8 to 12
  points for three models, and Claude Haiku keeps to the cap (72% to 97%). Changes 2 and 3
  also touch the statements, because the role texts are part of every prompt, so the
  statement results show changes 2, 3 and 5 together.

### How the changes were run

The changes were made in three rounds to save time: changes 2, 3 and the first version
of 4 together, then change 5, then the second version of 2 and 4 with the reasoning
wording. Each change targets its own eval set (imposter clues, civilian clues, debriefs,
statements), so a round still measures one change per eval set, except for the
statements as described above. The baseline of Mistral Small was run twice, because the
first run hit a metric bug: Mistral wraps its JSON in a Markdown code fence, which ADK
accepts and the metrics now accept too.

## Next

- **Imposters saying the word** is the largest remaining problem for Gemini Flash-Lite,
  Claude Haiku and Mistral Small (77 to 89% of imposter clues keep the word secret). Two
  prompt versions did not fix it, so this is where `adk optimize` (GEPA) is worth its
  cost: the imposter clue and `word_said` eval sets give a metric with headroom. GEPA only
  rewrites a fixed instruction, so the player instruction first needs a fixed strategy
  text split from the rendered situation. Choosing models for the imposter seat is the
  other lever, since Gemini Flash no longer fails.
- **Imposter clues stand out.** The blends-in rubric passes only 57 to 73%, unchanged by
  the prompts.
- **Clues still give the word away** in about one in five civilian clue turns
  (`clue_keeps_word_hidden`), the measure behind "the imposter guesses the word".
- **Claude Haiku's debriefs** stay above 80 words. A lower `max_output_tokens` for the
  debrief phase in the catalog would enforce it.
- **More data.** Votes and guesses have no eval sets, and new games add cases with
  `make eval-harvest` and `make eval-sets`. The traces of Cloud Run games are missing
  (#36).
