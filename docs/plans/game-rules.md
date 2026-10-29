# Game rules

The rules of [imposter.app](https://imposter.app/) are loose because humans fill the gaps.
Agents need a precise state machine. This file is the source of truth for the engine
(`src/imposter/engine/`). It is pure Python: no ADK, no LLM calls, no I/O.

## Setup (`GameConfig`)

Options on the setup screen are kept few and clear. Defaults in bold.

| Option | Values | Notes |
|---|---|---|
| Secret word mode | **random from category**, typed, generated ("surprise me") | See `models-and-judge.md` §Words |
| Category | one of the built-in categories | Required for random; optional for typed; returned by the generator |
| Players | 3–8 seats, each a catalog model | The same model may appear several times |
| Imposters | **1**, up to `floor((players - 1) / 2)` | Multi-imposter works in the engine; UI polish is future work |
| Identity mode | `seat`, **`names`**, `models` | See `models-and-judge.md` §Identity |
| Public category | **on**, off | Everyone, including the imposter, knows the category |
| Imposter hint | **off**, on | A related word generated at setup, shown to the imposter only |
| Clue rounds | **2** (1–3) | |
| Discussion rounds | **2** (0–3) | |
| Advanced (collapsed) | statement cap **100** words, reasoning cap **60** words, token budget **200k**, temperature override | |

Seat order is randomised at setup. Imposters are chosen uniformly at random. A seed may be
given for reproducible role assignment (the LLM output itself is not reproducible).

## Phases

```
SETUP → CLUE(1..C) → DISCUSSION(1..D) → VOTE → RESOLUTION → GUESS → OUTCOME → DEBRIEF → DONE
                                                                        (ABORTED from any phase)
```

1. **Setup**: word, category, hint, roles, seat order and names are fixed. Event:
   `game_started` (public part) plus per-player `role_assigned` (private).
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
   - Imposter not caught: **imposter wins**.
   - Imposter caught but guessed the word: **imposter steals the win**.
   - Imposter caught and guessed wrong: **civilians win**.
8. **Debrief** (parallel): the true roles and word are revealed to every player, who is
   asked to reflect on its clues, statements and vote. The engine records the reflections
   but they do not change the outcome.

## Validation and limits

- **Clue**: one word after trimming (letters, digits, internal hyphens or apostrophes),
  not equal to the secret word after normalisation, not a repeat of an earlier clue, not a
  trivial derivative of the word (the judge decides, see `models-and-judge.md` §Judge).
  Code checks run first; the judge is only consulted when code checks pass. An invalid
  clue gets one retry with the reason, then becomes `pass`.
- **Statement**: at most 100 words. Enforced in the prompt and by truncation in code
  (with a `truncated` flag on the event).
- **Private reasoning**: at most 60 words, truncated the same way.
- **Vote**: must name another living player by its display name; an invalid vote gets one
  retry, then counts as an abstention. Self-votes are invalid.
- **Guess**: free text, judged by exact match after normalisation (lowercase, strip,
  simple singular/plural) and otherwise by the judge (synonym or equivalent).

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
`game_started`, `role_assigned`, `phase_started`, `turn_started`, `clue_given`,
`statement_made`, `vote_cast` (private until resolution), `votes_revealed`,
`guess_made`, `guess_judged`, `outcome`, `reflection`, `player_error`, `usage` (tokens and
cost), `game_aborted`, `game_finished`. Private reasoning travels on the same event as the
public action, in a private field that the public projection drops.

The event log is the single source of truth for both the UI and the export file.

## Views (information hiding)

`GameState.view_for(seat) -> PlayerView` builds what one player may see: rules, own seat
and name, own role, the word (civilians only), the hint (imposter only, if on), the
category (if public), number of imposters, other players (by identity mode), the public
transcript so far, and that player's own scratchpad. Nothing else.

Invariants, enforced with Hypothesis property tests over random configs and scripted
games:

- An imposter's view, and the prompt rendered from it, never contains the secret word.
- No view contains another player's private reasoning or scratchpad.
- No view contains any vote before `votes_revealed`.
- The public projection of the event log contains no private fields.
