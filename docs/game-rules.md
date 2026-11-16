# Game rules

This page is the reference for the rules of the game as the engine in
`src/imposter/engine/` plays them. The rules of [imposter.app](https://imposter.app/) are
loose because humans fill the gaps, and agents need a precise state machine. The engine
is pure Python with pydantic. It imports no ADK, calls no model and does no I/O.
[`architecture.md`](architecture.md) explains how the game workflow drives it.

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
| `engine/game.py` | The `Game` class with its queries, checks (`rejection`), actions (`start_turn`, `submit`), `view_for` and `snapshot`, plus `Seat`, `GameSnapshot`, `ActionRejection` and `InvalidActionError`. |
| `engine/responses.py` | The structured response of each phase (`ClueResponse` and the others) and `PHASE_RESPONSE_TYPES`. |
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
| Secret word mode | **random from category**, typed, generated ("surprise me") | See [`architecture.md`](architecture.md#words). |
| Category | one of the built-in categories | It is required for a random word, optional for a typed word and returned by the generator. |
| Players | 3–8 seats, each a catalog model | The same model may appear several times |
| Imposters | **1**, up to `floor((players - 1) / 2)` | Several imposters work in the engine. The web app does not show teams yet. |
| Chosen imposters | **none**, or up to the number of imposters | A player marked `imposter` in its `PlayerConfig` is an imposter wherever its seat ends up, and the remaining imposters are random |
| Identity mode | `seat`, **`names`**, `models` | See [Identity modes](#identity-modes). |
| Public category | on, **off** | Everyone, including the imposter, knows the category. It is off by default, because with a concrete public category one clue was enough for the imposter to infer the word in a real game. |
| Imposter hint | **off**, on | A related word generated at setup, shown to the imposter only |
| Model clue check | **on**, off | A model judges every clue that passes the code checks, to catch synonyms and translations. Off saves one model call per clue, and the code checks still run. |
| Clue rounds | **2** (1–3) | |
| Discussion rounds | **2** (0–3) | |
| Advanced (collapsed) | statement cap **100** words, reasoning cap **60** words, token budget **200k**, temperature override | |

Seat order is randomized at setup. Imposters are chosen uniformly at random among the
players that are not chosen as imposters. A seed makes the seat order and the roles
reproducible, while the answers of the models are not. Seats are numbered from 0 after
shuffling, so the seat number is also the turn order.

`GameConfig` rejects options outside these limits when it is created. The API reports
that as an error event at the start of the run, and the CLI as a bad parameter.

### Identity modes

`identity_mode` decides how players are named in prompts and in the public transcript.

| Mode | Names | What players learn |
|---|---|---|
| `seat` | Player 1 to Player N | They learn nothing about their opponents. |
| `names` (default) | Alice, Bob, Charlie, Dave and so on, in seat order | They learn nothing about their opponents. |
| `models` | The display names of the models, numbered when repeated (`Claude Sonnet #2`) | They learn which model each opponent is. |

The web app always knows the model behind each seat. The mode is recorded on the root
span of the game's trace, so traces can be filtered to compare how models play when
they know who is who.

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
  imposter saying the word loses the game for the team. An imposter who believes it
  knows the word must give a related clue instead, which is exactly what the game asks
  of everyone.
- **Never repeat a clue.** A clue may not repeat any earlier clue of any player,
  including the player's own, after normalization. The clue task lists every word
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
   for the most votes, nobody is caught. With several imposters, see
   [Multiple imposters](#multiple-imposters).
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

- **Clue**: a clue that is or contains the secret word after normalization (also as part
  of a longer word or of several words) ends the game, as [Phases](#phases) describes. Otherwise it must be
  one word after trimming (letters, digits, internal hyphens or apostrophes), not a
  repeat of an earlier clue (own clues included), and not a trivial derivative of the
  word, which the judge decides ([`architecture.md`](architecture.md#judge)). The code
  checks run first, and the judge is only consulted when they pass. An invalid clue gets one retry with the
  reason, then becomes `pass`. Exception: when an imposter's clue is rejected by the
  judge for being too close to the word, it passes at once without a retry or a reason,
  since the reason would hint at the word.
- **Statement**: at most 100 words. Enforced in the prompt and by truncation in code
  (with a `truncated` flag on the event). A statement that says the secret word as a
  whole word (including simple plurals) after truncation ends the game.
- **Private reasoning**: at most 60 words, truncated the same way.
- **Vote**: must name another player by its display name. An invalid vote gets one
  retry, then counts as an abstention. Self-votes are invalid.
- **Guess**: free text, judged by exact match after normalization (lowercase, strip,
  simple singular/plural) and otherwise by the judge (synonym or equivalent).

The engine never calls the judge itself, to stay pure: the `play_turn` node of the game
workflow (`orchestration/workflow.py`) consults it and passes the verdict in, for example
`game.submit(..., judge_verdict=True)`.

## Multiple imposters

The engine supports `k` imposters. Each player still casts one vote, and the `k` players with
the most votes are caught, with ties at the boundary resolved by catching nobody at that
rank. Each imposter guesses, and the imposters win as a team if any imposter is not caught or
any caught imposter guesses the word. Imposters do not know each other. The engine tests
cover this mode, and the web app does not show teams yet.

## Events

Every state change is a `GameEvent` (pydantic, discriminated by `type`) with `game_id`,
`seq` (monotonic), `phase`, `timestamp`, and a `visibility`: `public` (anyone), `private`
(one seat, shown only in god mode or after the reveal) or `system`. Main types:
`game_started`, `phase_started`, `turn_started`, `clue_given`, `statement_made`,
`vote_cast` (private until resolution), `votes_revealed`, `guess_made` (with the verdict
and whether it came from an exact match or the judge), `secret_word_said` (the seat is
public, the text private), `outcome` (with `word_said_by`), `reflection`,
`player_error`, `usage` (tokens), `game_aborted`, `game_finished`. Private reasoning
travels on the same event as the public action, in a private field that the public projection drops. The `outcome` event
reveals the word publicly. Before it, no public projection contains the word.

The event log is the single source of truth for the web app, the CLI and the export
file. `game.snapshot()` returns the setup with the log as data, and `Game.load` rebuilds
the same game from it, which is how the game is kept in the state of its ADK session.

## Views (information hiding)

`game.view_for(seat) -> PlayerView` builds what one player may see: rules, own seat
and name, own role, the word (civilians only), the hint (imposter only, if on), the
category (if public), number of imposters, other players (by identity mode), the public
transcript so far (clues, statements and the votes once they are revealed), and that
player's own scratchpad. Nothing else. Guesses are not in the transcript, so with several
imposters a correct guess cannot help a later imposter. Once the outcome is decided, the
view also carries a reveal (word, category, imposters, guesses, outcome) for the debrief.
A seat's own vote stays out of its scratchpad until the votes are revealed.

These invariants are enforced with Hypothesis property tests over random configs and
games with random players (`tests/engine/test_leaks.py`):

- An imposter's view, and the prompt rendered from it, never contains the secret word.
- No view contains another player's private reasoning or scratchpad.
- No view contains any vote before `votes_revealed`.
- The public projection of the event log contains no private fields.

## What the engine rejects

| Situation | Result |
|---|---|
| Options outside the limits of [Setup](#setup), such as two imposters among four players | `GameConfig` raises a validation error, and no game is created. |
| The imposter hint is on and the secret has no hint, or the hint is the word | `Game.create` raises `ValueError`. |
| A seat starts a turn or submits when it is not its turn, or in another phase | The method raises `InvalidActionError`, and the game does not change. |
| A clue or vote that breaks a rule | `game.rejection` returns an `ActionRejection` with a reason that is safe to show the player. `game.submit` then records the fallback of the phase: a pass, an empty statement, an abstention, an empty guess or an empty reflection. |
| The tokens of a game pass its budget | `game.record_usage` appends `game_aborted`, and the game is over in phase `aborted`. |
| `game.abort` on a game that is over | The method raises `InvalidActionError`. |
