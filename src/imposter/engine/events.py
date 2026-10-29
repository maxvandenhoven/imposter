from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from imposter.engine.config import GameOutcome, GamePhase, IdentityMode, PlayerRole


class EventVisibility(StrEnum):
    """Who may see an event in audience mode.

    `PUBLIC` events are shown to anyone (with private fields dropped), `PRIVATE` events
    belong to one seat and are shown only in god mode or after the reveal, and `SYSTEM`
    events describe the run itself (errors, usage) rather than the game.
    """

    PUBLIC = "public"
    PRIVATE = "private"
    SYSTEM = "system"


class PublicSeat(BaseModel):
    """A seat as everyone at the table knows it.

    Attributes:
        seat: The 0-based seat number, which is also the turn order.
        name: The display name of the seat under the identity mode.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    name: str


class PublicVote(BaseModel):
    """One vote, as revealed at the resolution.

    Attributes:
        voter: The seat that voted.
        target: The seat voted for, or `None` for an abstention.
    """

    model_config = ConfigDict(frozen=True)

    voter: int
    target: int | None


class GameEventBase(BaseModel):
    """Fields shared by every game event.

    Subclasses list the names of fields that must never reach the audience in
    `private_fields`; `public_projection` drops them.

    Attributes:
        game_id: The game the event belongs to.
        seq: The 0-based position of the event in the event log, strictly increasing.
        phase: The phase in which the event happened.
        round: The round of the phase, for clue and discussion phases.
        timestamp: When the event was created.
        visibility: Who may see the event in audience mode.
    """

    model_config = ConfigDict(frozen=True)

    private_fields: ClassVar[frozenset[str]] = frozenset()

    game_id: str
    seq: int = Field(ge=0)
    phase: GamePhase
    round: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    visibility: EventVisibility = EventVisibility.PUBLIC

    def public_projection(self) -> dict[str, Any] | None:
        """Get the event as the audience may see it.

        Returns:
            The JSON-ready event without its private fields, or `None` for a private
            event, which the audience does not see at all.
        """
        if self.visibility is EventVisibility.PRIVATE:
            return None

        return self.model_dump(mode="json", exclude=set(self.private_fields))


class GameStartedEvent(GameEventBase):
    """The setup is fixed: seats, names and options, with the secrets as private fields.

    Attributes:
        identity_mode: How players are named.
        seats: The seats in turn order.
        imposter_count: The number of imposters.
        clue_rounds: The number of clue rounds.
        discussion_rounds: The number of discussion rounds.
        public_category: The category, when it is public.
        word: The secret word (private).
        category: The category, also when it is not public (private).
        hint: The imposter hint, if any (private).
        seat_models: The model id behind each seat, in seat order (private).
    """

    private_fields: ClassVar[frozenset[str]] = frozenset(
        {"word", "category", "hint", "seat_models"}
    )

    type: Literal["game_started"] = "game_started"
    identity_mode: IdentityMode
    seats: list[PublicSeat]
    imposter_count: int
    clue_rounds: int
    discussion_rounds: int
    public_category: str | None
    word: str
    category: str | None
    hint: str | None
    seat_models: list[str]


class RoleAssignedEvent(GameEventBase):
    """One seat learns its role.

    Attributes:
        seat: The seat.
        role: The role of the seat (private).
    """

    private_fields: ClassVar[frozenset[str]] = frozenset({"role"})

    type: Literal["role_assigned"] = "role_assigned"
    visibility: EventVisibility = EventVisibility.PRIVATE
    seat: int
    role: PlayerRole


class PhaseStartedEvent(GameEventBase):
    """A phase or round started; `phase` and `round` name it."""

    type: Literal["phase_started"] = "phase_started"


class TurnStartedEvent(GameEventBase):
    """A seat is asked to act.

    Attributes:
        seat: The seat whose turn starts.
    """

    type: Literal["turn_started"] = "turn_started"
    seat: int


class ClueGivenEvent(GameEventBase):
    """A seat gave its clue for the round.

    Attributes:
        seat: The seat.
        clue: The clue, or `None` when the seat passed.
        rejection_reason: Why the last attempt was rejected, when the seat passed after
            an invalid clue (private).
        private_reasoning: The reasoning of the seat (private).
        reasoning_truncated: Whether the reasoning was cut to the cap (private).
    """

    private_fields: ClassVar[frozenset[str]] = frozenset(
        {"rejection_reason", "private_reasoning", "reasoning_truncated"}
    )

    type: Literal["clue_given"] = "clue_given"
    seat: int
    clue: str | None
    rejection_reason: str | None = None
    private_reasoning: str
    reasoning_truncated: bool = False


class StatementMadeEvent(GameEventBase):
    """A seat made its public statement in a discussion round.

    Attributes:
        seat: The seat.
        statement: The statement, truncated and with the secret word redacted.
        truncated: Whether the statement was cut to the cap.
        private_reasoning: The reasoning of the seat (private).
        reasoning_truncated: Whether the reasoning was cut to the cap (private).
    """

    private_fields: ClassVar[frozenset[str]] = frozenset(
        {"private_reasoning", "reasoning_truncated"}
    )

    type: Literal["statement_made"] = "statement_made"
    seat: int
    statement: str
    truncated: bool = False
    private_reasoning: str
    reasoning_truncated: bool = False


class VoteCastEvent(GameEventBase):
    """A seat cast its secret vote, kept private until the votes are revealed.

    Attributes:
        seat: The voting seat.
        target: The seat voted for, or `None` for an abstention (private).
        private_reasoning: The reasoning of the seat (private).
        reasoning_truncated: Whether the reasoning was cut to the cap (private).
    """

    private_fields: ClassVar[frozenset[str]] = frozenset(
        {"target", "private_reasoning", "reasoning_truncated"}
    )

    type: Literal["vote_cast"] = "vote_cast"
    visibility: EventVisibility = EventVisibility.PRIVATE
    seat: int
    target: int | None
    private_reasoning: str
    reasoning_truncated: bool = False


class VotesRevealedEvent(GameEventBase):
    """All votes are revealed and tallied.

    Attributes:
        votes: Every vote, in seat order.
        counts: The number of votes per seat, as a list indexed by seat.
        caught: The caught seats, possibly none.
    """

    type: Literal["votes_revealed"] = "votes_revealed"
    votes: list[PublicVote]
    counts: list[int]
    caught: list[int]


class GuessMadeEvent(GameEventBase):
    """An imposter guessed the word.

    Attributes:
        seat: The imposter seat.
        guess: The guess, empty when the imposter gave none.
        private_reasoning: The reasoning of the seat (private).
        reasoning_truncated: Whether the reasoning was cut to the cap (private).
    """

    private_fields: ClassVar[frozenset[str]] = frozenset(
        {"private_reasoning", "reasoning_truncated"}
    )

    type: Literal["guess_made"] = "guess_made"
    seat: int
    guess: str
    private_reasoning: str
    reasoning_truncated: bool = False


class GuessJudgedEvent(GameEventBase):
    """A guess was judged against the secret word.

    Attributes:
        seat: The imposter seat.
        correct: Whether the guess counts as the word.
        method: `exact` for a match after normalisation, `judge` when the injected judge
            decided, `none` when there was no exact match and no judge verdict.
    """

    type: Literal["guess_judged"] = "guess_judged"
    seat: int
    correct: bool
    method: Literal["exact", "judge", "none"]


class OutcomeEvent(GameEventBase):
    """The winner is decided and the secrets are revealed.

    Attributes:
        outcome: How the game ended.
        word: The secret word.
        imposters: The imposter seats.
        caught: The caught seats.
    """

    type: Literal["outcome"] = "outcome"
    outcome: GameOutcome
    word: str
    imposters: list[int]
    caught: list[int]


class ReflectionEvent(GameEventBase):
    """A seat reflected on its play after the reveal.

    Attributes:
        seat: The seat.
        reflection: The reflection.
    """

    type: Literal["reflection"] = "reflection"
    seat: int
    reflection: str


class PlayerErrorEvent(GameEventBase):
    """A player failed to produce a valid action; a fallback may have been used.

    Attributes:
        seat: The seat.
        message: What went wrong.
    """

    type: Literal["player_error"] = "player_error"
    visibility: EventVisibility = EventVisibility.SYSTEM
    seat: int
    message: str


class UsageEvent(GameEventBase):
    """Tokens used by one turn.

    Attributes:
        seat: The seat that used the tokens.
        model_id: The model that used the tokens.
        input_tokens: The prompt tokens.
        output_tokens: The completion tokens.
        thinking_tokens: The thinking tokens.
        total_tokens: The tokens used by the whole game so far.
    """

    type: Literal["usage"] = "usage"
    visibility: EventVisibility = EventVisibility.SYSTEM
    seat: int
    model_id: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int


class GameAbortedEvent(GameEventBase):
    """The game stopped before its end.

    Attributes:
        reason: Why the game was aborted.
    """

    type: Literal["game_aborted"] = "game_aborted"
    reason: str


class GameFinishedEvent(GameEventBase):
    """The game is over, including the debrief.

    Attributes:
        outcome: How the game ended.
    """

    type: Literal["game_finished"] = "game_finished"
    outcome: GameOutcome


type GameEvent = Annotated[
    GameStartedEvent
    | RoleAssignedEvent
    | PhaseStartedEvent
    | TurnStartedEvent
    | ClueGivenEvent
    | StatementMadeEvent
    | VoteCastEvent
    | VotesRevealedEvent
    | GuessMadeEvent
    | GuessJudgedEvent
    | OutcomeEvent
    | ReflectionEvent
    | PlayerErrorEvent
    | UsageEvent
    | GameAbortedEvent
    | GameFinishedEvent,
    Field(discriminator="type"),
]
"""Any game event, discriminated by its `type` field."""

GAME_EVENT_ADAPTER: TypeAdapter[GameEvent] = TypeAdapter(GameEvent)
"""Validates and serialises a single `GameEvent`, for example from an export file."""
