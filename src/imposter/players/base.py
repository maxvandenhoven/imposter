from collections.abc import Callable
from typing import Protocol

from google.adk.agents.context import Context
from pydantic import BaseModel, ConfigDict, Field

from imposter.engine.game import Game
from imposter.engine.responses import PhaseResponse
from imposter.engine.views import PlayerView


class TurnUsage(BaseModel):
    """The tokens one model call used.

    Attributes:
        model_id: The model that used the tokens.
        input_tokens: The prompt tokens.
        output_tokens: The completion tokens.
        thinking_tokens: The thinking tokens.
    """

    model_config = ConfigDict(frozen=True)

    model_id: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    thinking_tokens: int = Field(default=0, ge=0)


type UsageRecorder = Callable[[TurnUsage], None]
"""Takes the tokens of each model call of a turn, also of calls that fail afterwards."""


class PlayerProtocol(Protocol):
    """A participant in a game, backed by a model, a script or chance.

    A player gets only the view of its own seat, so it cannot see more than the rules
    allow. Which phase to act in and the limits are part of the view. A turn runs in
    the turn node of its seat, whose context a player uses to run an ADK agent as a
    child node, so the agent's events and spans are part of the game run.
    """

    async def take_turn(
        self,
        *,
        ctx: Context,
        view: PlayerView,
        record_usage: UsageRecorder,
        retry_reason: str | None = None,
    ) -> PhaseResponse:
        """Act in the phase of the view.

        Args:
            ctx: The context of the turn node.
            view: Everything the seat may know.
            record_usage: Takes the tokens of each model call of the turn.
            retry_reason: Why the previous attempt in this turn was rejected, if any.

        Returns:
            The structured output of the turn. A player that cannot answer raises.
        """
        ...


class PlayerSeatingProtocol(Protocol):
    """Decides who plays each seat of a game."""

    def player_for(self, *, game: Game, seat: int) -> PlayerProtocol:
        """Get the player of a seat.

        Args:
            game: The game.
            seat: The seat.

        Returns:
            The player that takes the turns of the seat.
        """
        ...
