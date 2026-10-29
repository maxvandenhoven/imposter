import random
from collections.abc import Sequence

from imposter.config import GamePhase, PlayerRole
from imposter.engine.views import PlayerView, other_players
from imposter.players.base import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PhaseResponse,
    PlayerResponse,
    TurnUsage,
    VoteResponse,
)
from imposter.utils.text import normalize_word

RANDOM_VOCABULARY = (
    "bright",
    "cold",
    "round",
    "small",
    "heavy",
    "soft",
    "loud",
    "green",
    "fast",
    "old",
    "sharp",
    "sweet",
    "wooden",
    "metal",
    "outdoor",
    "kitchen",
    "summer",
    "winter",
    "travel",
    "music",
    "water",
    "paper",
    "tiny",
    "giant",
    "smooth",
    "noisy",
    "quiet",
    "useful",
    "classic",
    "modern",
)
"""Words a `RandomPlayer` draws its clues and guesses from."""

type ScriptStep = PhaseResponse | PlayerResponse | Exception
"""One canned turn of a `ScriptedPlayer`: an output, a full response or an error."""


class ScriptedPlayer:
    """A player that replays canned turns, for tests.

    Each call to `take_turn` consumes the next step of the script. An exception step is
    raised instead of returned, to simulate a failing model.

    Attributes:
        script: The remaining canned turns.
        usage: The usage reported with every output that is not a full response.
        views: The views the player received, in order.
        retry_reasons: The retry reasons the player received, in order.
    """

    def __init__(
        self, *, script: Sequence[ScriptStep], usage: TurnUsage | None = None
    ) -> None:
        """Initialize the player.

        Args:
            script: The canned turns, in order.
            usage: The usage reported with every output that is not a full response.
        """
        self.script = list(script)
        self.usage = usage
        self.views: list[PlayerView] = []
        self.retry_reasons: list[str | None] = []

    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse:
        """Replay the next canned turn.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt in this turn was rejected, if any.

        Returns:
            The next canned response.

        Raises:
            LookupError: When the script is exhausted.
        """
        self.views.append(view)
        self.retry_reasons.append(retry_reason)

        if not self.script:
            message = (
                f"The script of seat {view.seat} is exhausted in phase {view.phase}."
            )
            raise LookupError(message)

        step = self.script.pop(0)

        if isinstance(step, Exception):
            raise step

        if isinstance(step, PlayerResponse):
            return step

        return PlayerResponse(output=step, usage=self.usage)


class RandomPlayer:
    """A player that acts at random, for tests and offline demos.

    Its private reasoning always contains a marker unique to the seat and turn, and for
    civilians the secret word, so leak tests can detect reasoning in other views. With a
    `blunder_rate`, it sometimes gives invalid output: a clue of two words or equal to
    the word, a statement that says the word, or a vote for itself.

    Attributes:
        rng: The random number generator, the only source of randomness.
        blunder_rate: The probability of an invalid output per turn.
        usage: The usage reported with every turn.
        views: The views the player received, in order.
    """

    def __init__(
        self, *, seed: int, blunder_rate: float = 0.0, usage: TurnUsage | None = None
    ) -> None:
        """Initialize the player.

        Args:
            seed: The seed of the random number generator.
            blunder_rate: The probability of an invalid output per turn.
            usage: The usage reported with every turn.
        """
        self.rng = random.Random(seed)
        self.blunder_rate = blunder_rate
        self.usage = usage
        self.views: list[PlayerView] = []

    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse:
        """Act at random in the phase of the view.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt was rejected, ignored by this player.

        Returns:
            A random response for the phase.
        """
        self.views.append(view)
        output = self.output_for(
            view=view,
            blunder=self.rng.random() < self.blunder_rate,
            reasoning=self.reasoning_for(view=view, turn=len(self.views)),
        )

        return PlayerResponse(output=output, usage=self.usage)

    def output_for(
        self, *, view: PlayerView, blunder: bool, reasoning: str
    ) -> PhaseResponse:
        """Pick a random output for the phase of a view.

        Args:
            view: Everything the seat may know.
            blunder: Whether to give an invalid output where the phase allows one.
            reasoning: The private reasoning to attach.

        Returns:
            The structured output.
        """
        match view.phase:
            case GamePhase.CLUE:
                return ClueResponse(
                    clue=self.clue_for(view=view, blunder=blunder),
                    private_reasoning=reasoning,
                )
            case GamePhase.DISCUSSION:
                statement = (
                    f"I find {self.rng.choice(other_players(view)).name} suspicious."
                )

                if blunder and view.word:
                    statement += f" The word is obviously {view.word}."

                return DiscussionResponse(
                    statement=statement, private_reasoning=reasoning
                )
            case GamePhase.VOTE:
                target = (
                    view.name if blunder else self.rng.choice(other_players(view)).name
                )
                return VoteResponse(vote_for=target, private_reasoning=reasoning)
            case GamePhase.GUESS:
                heard = [clue.clue for clue in view.clues if clue.clue]
                guess = self.rng.choice(heard or list(RANDOM_VOCABULARY))
                return GuessResponse(guess=guess, private_reasoning=reasoning)
            case _:
                return DebriefResponse(reflection="I played at random.")

    def clue_for(self, *, view: PlayerView, blunder: bool) -> str:
        """Pick a clue that has not been given yet, or an invalid one when blundering.

        Args:
            view: Everything the seat may know.
            blunder: Whether to give an invalid clue.

        Returns:
            The clue.
        """
        if blunder:
            return view.word if view.word else "two words"

        given = {normalize_word(clue.clue) for clue in view.clues if clue.clue}
        options = [word for word in RANDOM_VOCABULARY if word not in given]

        return self.rng.choice(options or ["something"])

    def reasoning_for(self, *, view: PlayerView, turn: int) -> str:
        """Write private reasoning that is easy to trace in leak tests.

        Args:
            view: Everything the seat may know.
            turn: The 1-based number of the turn of this player.

        Returns:
            The reasoning, with a marker unique to the seat and turn.
        """
        marker = f"reasoning-seat{view.seat}-turn{turn}"

        if view.role is PlayerRole.CIVILIAN and view.word:
            return f"{marker} I know the word is {view.word}."

        return f"{marker} I do not know the word."
