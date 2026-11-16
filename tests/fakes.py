"""Fake players for tests: scripted or random, and a pure loop that plays them."""

import random
from collections.abc import Callable, Sequence

from google.adk.agents.context import Context

from imposter.config import GamePhase, PlayerRole
from imposter.engine.game import Game
from imposter.engine.responses import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PhaseResponse,
    VoteResponse,
)
from imposter.engine.views import PlayerView, other_players
from imposter.players.base import PlayerProtocol, TurnUsage, UsageRecorder
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

type ScriptStep = PhaseResponse | Exception
"""One canned turn of a `ScriptedPlayer`: a response, or an error to raise."""

type PlayersFactory = Callable[[Game], Sequence[PlayerProtocol]]
"""Builds the players of a game, one per seat in seat order."""


class ScriptedPlayer:
    """A player that replays canned turns.

    Each turn consumes the next step of the script. An exception step is raised instead
    of returned, to simulate a failing model.

    Attributes:
        script: The remaining canned turns.
        usage: The usage recorded with every turn, also a failing one.
        views: The views the player received, in order.
        retry_reasons: The retry reasons the player received, in order.
    """

    def __init__(
        self, *, script: Sequence[ScriptStep], usage: TurnUsage | None = None
    ) -> None:
        self.script = list(script)
        self.usage = usage
        self.views: list[PlayerView] = []
        self.retry_reasons: list[str | None] = []

    def respond(self, view: PlayerView, retry_reason: str | None = None) -> PhaseResponse:
        """Replay the next canned turn."""
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

        return step

    async def take_turn(
        self,
        *,
        ctx: Context,
        view: PlayerView,
        record_usage: UsageRecorder,
        retry_reason: str | None = None,
    ) -> PhaseResponse:
        """Replay the next canned turn in a turn node."""
        if self.usage is not None:
            record_usage(self.usage)

        return self.respond(view, retry_reason)


class RandomPlayer:
    """A player that acts at random.

    Its private reasoning always contains a marker unique to the seat and turn, and for
    civilians the secret word, so leak tests can detect reasoning in other views. With a
    `blunder_rate`, it sometimes gives invalid output: a clue of two words or equal to
    the word, a statement that says the word, or a vote for itself.

    Attributes:
        rng: The random number generator, the only source of randomness.
        blunder_rate: The probability of an invalid output per turn.
        usage: The usage recorded with every turn.
        views: The views the player received, in order.
    """

    def __init__(
        self, *, seed: int, blunder_rate: float = 0.0, usage: TurnUsage | None = None
    ) -> None:
        self.rng = random.Random(seed)
        self.blunder_rate = blunder_rate
        self.usage = usage
        self.views: list[PlayerView] = []

    def respond(self, view: PlayerView, retry_reason: str | None = None) -> PhaseResponse:
        """Act at random in the phase of the view, ignoring the retry reason."""
        self.views.append(view)

        return self.output_for(
            view=view,
            blunder=self.rng.random() < self.blunder_rate,
            reasoning=self.reasoning_for(view=view, turn=len(self.views)),
        )

    async def take_turn(
        self,
        *,
        ctx: Context,
        view: PlayerView,
        record_usage: UsageRecorder,
        retry_reason: str | None = None,
    ) -> PhaseResponse:
        """Act at random in a turn node."""
        if self.usage is not None:
            record_usage(self.usage)

        return self.respond(view, retry_reason)

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


class FakeSeating:
    """Seats the fake players of a factory, built once per game.

    Attributes:
        players_for: Builds the players of a game.
        players: The players of each game seated so far, by game id.
    """

    def __init__(self, players_for: PlayersFactory) -> None:
        self.players_for = players_for
        self.players: dict[str, Sequence[PlayerProtocol]] = {}

    def player_for(self, *, game: Game, seat: int) -> PlayerProtocol:
        """Get the fake player of a seat."""
        if game.game_id not in self.players:
            self.players[game.game_id] = self.players_for(game)

        return self.players[game.game_id][seat]


def random_players(game: Game) -> list[RandomPlayer]:
    """Seat a random player that reports 100 tokens per turn for every seat."""
    return [
        RandomPlayer(
            seed=seat.seat,
            usage=TurnUsage(
                model_id=seat.player.model_id, input_tokens=90, output_tokens=10
            ),
        )
        for seat in game.seats
    ]


def play_pure_step(
    *, game: Game, players: Sequence[ScriptedPlayer | RandomPlayer]
) -> None:
    """Play the next turn, or all turns of a parallel phase, on the engine alone."""
    seats = game.pending_seats[:1] if game.is_sequential else game.pending_seats

    for seat in seats:
        game.start_turn(seat)

    responses = [players[seat].respond(game.view_for(seat)) for seat in seats]

    for seat, response in zip(seats, responses, strict=True):
        rejection = game.rejection(seat=seat, response=response)
        game.submit(seat=seat, response=response, rejection=rejection)


def play_pure(*, game: Game, players: Sequence[ScriptedPlayer | RandomPlayer]) -> None:
    """Play a game to the end on the engine alone: no ADK, no retries, no judge."""
    while not game.is_over:
        play_pure_step(game=game, players=players)
