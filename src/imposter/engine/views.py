from pydantic import BaseModel, ConfigDict

from imposter.config import GameOutcome, GamePhase, PlayerRole
from imposter.engine.events import PublicSeat, PublicVote


class GameRules(BaseModel):
    """The numbers of the rules that every player is told.

    Attributes:
        player_count: The number of seats.
        imposter_count: The number of imposters.
        clue_rounds: The number of clue rounds.
        discussion_rounds: The number of discussion rounds.
        statement_word_cap: The maximum number of words in a statement.
        reasoning_word_cap: The maximum number of words of private reasoning.
    """

    model_config = ConfigDict(frozen=True)

    player_count: int
    imposter_count: int
    clue_rounds: int
    discussion_rounds: int
    statement_word_cap: int
    reasoning_word_cap: int


class PublicClue(BaseModel):
    """A clue in the public transcript.

    Attributes:
        round: The clue round.
        seat: The seat that gave the clue.
        clue: The clue, or `None` when the seat passed.
    """

    model_config = ConfigDict(frozen=True)

    round: int | None
    seat: int
    clue: str | None


class PublicStatement(BaseModel):
    """A discussion statement in the public transcript.

    Attributes:
        round: The discussion round.
        seat: The seat that made the statement.
        statement: The statement, truncated and with the secret word redacted.
        truncated: Whether the statement was cut to the cap.
    """

    model_config = ConfigDict(frozen=True)

    round: int | None
    seat: int
    statement: str
    truncated: bool


class VoteResult(BaseModel):
    """The revealed votes and who was caught.

    Attributes:
        votes: Every vote, in seat order.
        caught: The caught seats, possibly none.
    """

    model_config = ConfigDict(frozen=True)

    votes: list[PublicVote]
    caught: list[int]


class PublicGuess(BaseModel):
    """An imposter's guess, shown in the reveal.

    Attributes:
        seat: The imposter seat.
        guess: The guess.
        correct: Whether it counted as the word.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    guess: str
    correct: bool


class GameReveal(BaseModel):
    """Everything revealed to all players for the debrief.

    Attributes:
        word: The secret word.
        category: The category of the word, if known.
        imposters: The imposter seats.
        guesses: The guesses of the imposters.
        outcome: How the game ended.
    """

    model_config = ConfigDict(frozen=True)

    word: str
    category: str | None
    imposters: list[int]
    guesses: list[PublicGuess]
    outcome: GameOutcome


class ScratchpadEntry(BaseModel):
    """One earlier turn of a seat, as remembered in its private scratchpad.

    Attributes:
        phase: The phase of the turn.
        round: The round of the turn, if the phase has rounds.
        action: The public action the seat took, in a few words.
        private_reasoning: The reasoning the seat recorded with the action.
    """

    model_config = ConfigDict(frozen=True)

    phase: GamePhase
    round: int | None
    action: str
    private_reasoning: str


class PlayerView(BaseModel):
    """Everything one seat may know at a point in the game, and nothing else.

    Built by `Game.view_for`. The leak tests check the invariants of `game-rules.md`
    §Views on these objects.

    Attributes:
        game_id: The game.
        phase: The current phase.
        round: The current round, if the phase has rounds.
        rules: The numbers of the rules.
        seat: The seat of this player.
        name: The display name of this player.
        role: The role of this player.
        word: The secret word, for civilians only.
        hint: The imposter hint, for imposters only and only when enabled.
        category: The category, when public or after the reveal.
        players: All seats in turn order, including this one.
        clues: All clues given so far.
        statements: All discussion statements so far.
        vote_result: The revealed votes, once the votes are revealed.
        reveal: The true roles, word and outcome, during the debrief.
        scratchpad: This seat's own earlier turns and reasoning.
    """

    model_config = ConfigDict(frozen=True)

    game_id: str
    phase: GamePhase
    round: int | None
    rules: GameRules
    seat: int
    name: str
    role: PlayerRole
    word: str | None
    hint: str | None
    category: str | None
    players: list[PublicSeat]
    clues: list[PublicClue]
    statements: list[PublicStatement]
    vote_result: VoteResult | None
    reveal: GameReveal | None
    scratchpad: list[ScratchpadEntry]


def other_players(view: PlayerView) -> list[PublicSeat]:
    """List every seat except the viewer's own, the valid vote targets.

    Args:
        view: The view of a seat.

    Returns:
        The other seats, in seat order.
    """
    return [player for player in view.players if player.seat != view.seat]
