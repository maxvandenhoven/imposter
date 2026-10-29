# Game rules

The rules of [imposter.app](https://imposter.app/) are loose because humans fill the gaps.
Agents need a precise state machine. This file is the source of truth for the engine
(`src/imposter/engine/`). It is pure Python: no ADK, no LLM calls, no I/O.

## Engine shape

A game is a `Game` object: the config, the secret word, the seats and an append-only
event log. Its methods change it in place by appending events, for example
`game.start_turn(seat)` and `game.submit_clue(seat=..., clue=...)`, and the automatic
phases (resolution, outcome) run inside those methods. The event log is the only state
that changes: the current phase is the phase of the last event, `game.pending_seats`
lists who still has to act, and `game.view_for(seat)` builds what one seat may see, all
derived from the events. There is no second copy of the state that could drift away
from the log.

| Module | Holds |
|---|---|
| `engine/game.py` | The `Game` class with its queries, checks (`clue_rejection`, `vote_rejection`), actions and `view_for`, plus `Seat`, `ActionRejection` and `InvalidActionError`. |
| `engine/events.py` | The `GameEvent` types and `public_projection`. |
| `engine/views.py` | The `PlayerView` data types. |
| `config.py` | The shared enums and the `GameConfig`, `PlayerConfig` and `SecretWord` data types, at the package root because players, orchestration and the API use them too. |
| `utils/` | Small functions on plain values, also at the package root: seat names per identity mode (`names.py`), the phase flow (`phases.py`), vote counting and the outcome (`tally.py`), and word handling (`text.py`). |

## Setup

Options on the setup screen are kept few and clear. Defaults in bold. The word options
are resolved into a `SecretWord` (word, category, hint) before the game is created, so
`GameConfig` holds only the other options.

| Option | Values | Notes |
|---|---|---|
| Secret word mode | **random from category**, typed, generated ("surprise me") | See `models-and-judge.md` §Words |
| Category | one of the built-in categories | Required for random; optional for typed; returned by the generator |
| Players | 3–8 seats, each a catalog model | The same model may appear several times |
| Imposters | **1**, up to `floor((players - 1) / 2)` | Multi-imposter works in the engine; UI polish is future work |
| Identity mode | `seat`, **`names`**, `models` | See `models-and-judge.md` §Identity |
| Public category | on, **off** | Everyone, including the imposter, knows the category. Off by default since playtest 1 (`playtests.md`): with a concrete category, one clue was enough for the imposter to infer the word. |
| Imposter hint | **off**, on | A related word generated at setup, shown to the imposter only |
| Model clue check | **on**, off | A model judges every clue that passes the code checks, to catch synonyms and translations. Off saves one Flash-Lite call per clue, and code checks still run. |
| Clue rounds | **2** (1–3) | |
| Discussion rounds | **2** (0–3) | |
| Advanced (collapsed) | statement cap **100** words, reasoning cap **60** words, token budget **200k**, temperature override | |

Seat order is randomised at setup. Imposters are chosen uniformly at random. A seed may be
given for reproducible role assignment (the LLM output itself is not reproducible). Seats
are numbered from 0 after shuffling, so the seat number is also the turn order.

## Phases

```
SETUP → CLUE(1..C) → DISCUSSION(1..D) → VOTE → RESOLUTION → GUESS → OUTCOME → DEBRIEF → DONE
          └──────── secret word said ────────────────────────────────▶ OUTCOME
                                                                        (ABORTED from any phase)
```

Two rules hold in every clue and discussion turn and are stated prominently in the
prompts:

- **Never say the secret word.** A clue or statement that says the secret word ends the
  game at once, and the speaker's side loses: the imposters win when a civilian says it
  (`civilian_said_word`), the civilians win when an imposter says it
  (`imposter_said_word`). The remaining clue, discussion, vote and guess phases are
  skipped, the outcome is revealed and the debrief follows. With several imposters, any
  imposter saying the word loses the game for the team. This replaces the earlier rule
  that turned such a clue into a pass and redacted the word from statements (see
  `playtests.md`, playtest 1). An imposter who believes it knows the word must give a
  related clue instead, which is exactly what the game asks of everyone.
- **Never repeat a clue.** A clue may not repeat any earlier clue of any player,
  including the player's own, after normalisation. The clue task lists every word
  already used.

1. **Setup**: word, category, hint, roles, seat order and names are fixed. Event:
   `game_started`, with the word, the hint, the models and the imposters as private
   fields.
2. **Clue round r** (sequential, in seat order): each player gives exactly one word. Every
   player sees all earlier clues of all rounds.
3. **Discussion round r** (sequential, in seat order): each player gives one public
   statement of at most 100 words: accusations, defences, rebuttals. Round 2 exists so
   players can respond to accusations from round 1.
4. **Vote** (simultaneous and secret): each player names one other player. Votes are not
   visible to anyone (including other players' views) until the resolution.
5. **Resolution**: votes are revealed. The player with the most votes is caught. On a tie
   for the most votes, nobody is caught. With several imposters, see §Multiple imposters.
6. **Guess**: each imposter always gets exactly one guess at the word, whether caught or
   not. Guessing happens after the vote reveal, so the imposter knows whether it was
   caught.
7. **Outcome**:
   - Someone said the secret word: that player's side loses (see above).
   - Imposter not caught: **imposter wins**.
   - Imposter caught but guessed the word: **imposter steals the win**.
   - Imposter caught and guessed wrong: **civilians win**.
8. **Debrief** (parallel): the true roles and word are revealed to every player, who is
   asked to reflect on its clues, statements and vote. The engine records the reflections
   but they do not change the outcome.

## Validation and limits

- **Clue**: a clue that is or contains the secret word after normalisation (also as part
  of a longer word or of several words) ends the game, see §Phases. Otherwise it must be
  one word after trimming (letters, digits, internal hyphens or apostrophes), not a
  repeat of an earlier clue (own clues included), and not a trivial derivative of the
  word (the judge decides, see `models-and-judge.md` §Judge). Code checks run first; the
  judge is only consulted when code checks pass. An invalid clue gets one retry with the
  reason, then becomes `pass`. Exception: when an imposter's clue is rejected by the
  judge for being too close to the word, it passes at once without a retry or a reason,
  since the reason would hint at the word.
- **Statement**: at most 100 words. Enforced in the prompt and by truncation in code
  (with a `truncated` flag on the event). A statement that says the secret word as a
  whole word (including simple plurals) after truncation ends the game, see §Phases.
- **Private reasoning**: at most 60 words, truncated the same way.
- **Vote**: must name another living player by its display name; an invalid vote gets one
  retry, then counts as an abstention. Self-votes are invalid.
- **Guess**: free text, judged by exact match after normalisation (lowercase, strip,
  simple singular/plural) and otherwise by the judge (synonym or equivalent).

The engine never calls the judge itself, to stay pure: the turn loop in
`GameRunner` in `orchestration/runner.py` consults it and passes the verdict in, for example
`game.submit_guess(..., judge_verdict=True)`.

## Multiple imposters

The engine supports `k` imposters. Each player still casts one vote; the `k` players with
the most votes are caught, with ties at the boundary resolved by catching nobody at that
rank. Each imposter guesses; the imposters win as a team if any imposter is not caught or
any caught imposter guesses the word. Imposters do not know each other. UI polish for this
mode is future work; v1 tests cover the engine logic.

## Events

Every state change is an `GameEvent` (pydantic, discriminated by `type`) with `game_id`,
`seq` (monotonic), `phase`, `timestamp`, and a `visibility`: `public` (anyone), `private`
(one seat; shown only in god mode or after the reveal) or `system`. Main types:
`game_started`, `phase_started`, `turn_started`, `clue_given`, `statement_made`,
`vote_cast` (private until resolution), `votes_revealed`, `guess_made` (with the verdict
and whether it came from an exact match or the judge), `secret_word_said` (the seat is
public, the text private), `outcome` (with `word_said_by`), `reflection`,
`player_error`, `usage` (tokens and cost), `game_aborted`, `game_finished`. Private reasoning travels on the same event as the
public action, in a private field that the public projection drops. The `outcome` event
reveals the word publicly; before it, no public projection contains the word.

The event log is the single source of truth for both the UI and the export file.

## Views (information hiding)

`game.view_for(seat) -> PlayerView` builds what one player may see: rules, own seat
and name, own role, the word (civilians only), the hint (imposter only, if on), the
category (if public), number of imposters, other players (by identity mode), the public
transcript so far (clues and statements; the revealed votes once revealed), and that
player's own scratchpad. Nothing else. Guesses are not in the transcript, so with several
imposters a correct guess cannot help a later imposter. Once the outcome is decided, the
view also carries a reveal (word, category, imposters, guesses, outcome) for the debrief.
A seat's own vote stays out of its scratchpad until the votes are revealed.

Invariants, enforced with Hypothesis property tests over random configs and scripted
games:

- An imposter's view, and the prompt rendered from it, never contains the secret word.
- No view contains another player's private reasoning or scratchpad.
- No view contains any vote before `votes_revealed`.
- The public projection of the event log contains no private fields.
