import random
from collections.abc import Sequence

from imposter.engine.config import GamePhase, PlayerRole
from imposter.engine.rules import normalize_word
from imposter.engine.views import PlayerView
from imposter.players.base import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PhaseResponse,
    PlayerResponse,
    PlayerTask,
    TurnUsage,
    VoteResponse,
)

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
        seat: The seat the player sits at.
        script: The remaining canned turns.
        usage: The usage reported with every output that is not a full response.
        views: The views the player received, in order.
        tasks: The tasks the player received, in order.
    """

    def __init__(
        self, *, seat: int, script: Sequence[ScriptStep], usage: TurnUsage | None = None
    ) -> None:
        """Initialize the player.

        Args:
            seat: The seat the player sits at.
            script: The canned turns, in order.
            usage: The usage reported with every output that is not a full response.
        """
        self.seat = seat
        self.script = list(script)
        self.usage = usage
        self.views: list[PlayerView] = []
        self.tasks: list[PlayerTask] = []

    async def take_turn(self, view: PlayerView, task: PlayerTask) -> PlayerResponse:
        """Replay the next canned turn.

        Args:
            view: Everything the seat may know.
            task: The phase to act in and its limits.

        Returns:
            The next canned response.

        Raises:
            LookupError: When the script is exhausted.
        """
        self.views.append(view)
        self.tasks.append(task)

        if not self.script:
            message = f"the script of seat {self.seat} is exhausted in phase {task.phase}"
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
        seat: The seat the player sits at.
        rng: The random number generator, the only source of randomness.
        blunder_rate: The probability of an invalid output per turn.
        usage: The usage reported with every turn.
        views: The views the player received, in order.
        turns: The number of turns taken so far.
    """

    def __init__(
        self,
        *,
        seat: int,
        seed: int,
        blunder_rate: float = 0.0,
        usage: TurnUsage | None = None,
    ) -> None:
        """Initialize the player.

        Args:
            seat: The seat the player sits at.
            seed: The seed of the random number generator.
            blunder_rate: The probability of an invalid output per turn.
            usage: The usage reported with every turn.
        """
        self.seat = seat
        self.rng = random.Random(seed)
        self.blunder_rate = blunder_rate
        self.usage = usage
        self.views: list[PlayerView] = []
        self.turns = 0

    async def take_turn(self, view: PlayerView, task: PlayerTask) -> PlayerResponse:
        """Act at random in the current phase.

        Args:
            view: Everything the seat may know.
            task: The phase to act in and its limits.

        Returns:
            A random response for the phase.
        """
        self.views.append(view)
        self.turns += 1

        return PlayerResponse(
            output=self.output_for(view=view, task=task), usage=self.usage
        )

    def output_for(self, *, view: PlayerView, task: PlayerTask) -> PhaseResponse:
        """Pick a random output for a task.

        Args:
            view: Everything the seat may know.
            task: The phase to act in and its limits.

        Returns:
            The structured output.
        """
        blunder = self.rng.random() < self.blunder_rate
        reasoning = self.reasoning_for(view)

        match task.phase:
            case GamePhase.CLUE:
                return ClueResponse(
                    clue=self.clue_for(view=view, blunder=blunder),
                    private_reasoning=reasoning,
                )
            case GamePhase.DISCUSSION:
                suspect = self.rng.choice(view.other_players).name
                statement = f"I find {suspect} suspicious."

                if blunder and view.word:
                    statement += f" The word is obviously {view.word}."

                return DiscussionResponse(
                    statement=statement, private_reasoning=reasoning
                )
            case GamePhase.VOTE:
                target = (
                    view.name if blunder else self.rng.choice(view.other_players).name
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

    def reasoning_for(self, view: PlayerView) -> str:
        """Write private reasoning that is easy to trace in leak tests.

        Args:
            view: Everything the seat may know.

        Returns:
            The reasoning, with a marker unique to this seat and turn.
        """
        marker = f"reasoning-seat{self.seat}-turn{self.turns}"

        if view.role is PlayerRole.CIVILIAN and view.word:
            return f"{marker} I know the word is {view.word}."

        return f"{marker} I do not know the word."
