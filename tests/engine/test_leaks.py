"""Property tests for the information hiding invariants of `game-rules.md` §Views."""

import asyncio
import re
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from imposter.config import (
    GameConfig,
    GamePhase,
    IdentityMode,
    PlayerConfig,
    PlayerRole,
    SecretWord,
)
from imposter.engine.events import EventVisibility, OutcomeEvent, public_projection
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.orchestration.runner import GameRunner
from imposter.players.base import TurnUsage
from imposter.players.fake import RandomPlayer

SECRET_WORDS = ("giraffe", "volcano", "trumpet", "lantern", "glacier", "pretzel")
"""Secret words that appear in no name, vocabulary word or fixed text of the game."""

HINTS = ("savanna", "eruption", "brass", "candle", "frozen", "bakery")
"""Imposter hints, also distinct from everything else."""

MARKER_PATTERN = re.compile(r"reasoning-seat(\d+)")
"""Finds the seat in the reasoning markers that `RandomPlayer` writes."""


@dataclass(frozen=True)
class PlayedGame:
    """A finished random game and every view its players received.

    Attributes:
        game: The finished game.
        views: Every view handed to a player, including retries.
    """

    game: Game
    views: list[PlayerView]


@st.composite
def played_games(draw: st.DrawFn) -> PlayedGame:
    """Play a random game with random players, some of which blunder."""
    player_count = draw(st.integers(min_value=3, max_value=8))
    index = draw(st.integers(min_value=0, max_value=len(SECRET_WORDS) - 1))
    config = GameConfig(
        players=[
            PlayerConfig(model_id=f"model-{draw(st.integers(min_value=0, max_value=2))}")
            for _ in range(player_count)
        ],
        imposter_count=draw(st.integers(min_value=1, max_value=(player_count - 1) // 2)),
        identity_mode=draw(st.sampled_from(IdentityMode)),
        public_category=draw(st.booleans()),
        imposter_hint=draw(st.booleans()),
        clue_rounds=draw(st.integers(min_value=1, max_value=3)),
        discussion_rounds=draw(st.integers(min_value=0, max_value=3)),
        reasoning_word_cap=draw(st.integers(min_value=3, max_value=60)),
        seed=draw(st.integers()),
    )
    secret = SecretWord(word=SECRET_WORDS[index], category="things", hint=HINTS[index])
    game = Game.create(config=config, secret=secret)
    blunder_rate = draw(st.floats(min_value=0, max_value=0.5))
    seed = draw(st.integers())
    usage = TurnUsage(model_id="random", input_tokens=10)
    players = [
        RandomPlayer(seed=seed + seat.seat, blunder_rate=blunder_rate, usage=usage)
        for seat in game.seats
    ]
    asyncio.run(GameRunner(players=players).play(game))

    return PlayedGame(
        game=game, views=[view for player in players for view in player.views]
    )


def mentions(text: str, word: str) -> bool:
    """Check whether a text contains a word as a whole word, ignoring case."""
    return re.search(rf"\b{re.escape(word)}", text, re.IGNORECASE) is not None


@settings(max_examples=150, deadline=None)
@given(played=played_games())
def test_games_with_random_players_finish(played: PlayedGame) -> None:
    assert played.game.phase is GamePhase.DONE


@settings(max_examples=150, deadline=None)
@given(played=played_games())
def test_imposter_views_never_contain_the_word_before_the_reveal(
    played: PlayedGame,
) -> None:
    word = played.game.secret.word

    for view in played.views:
        if view.role is PlayerRole.IMPOSTER and view.reveal is None:
            assert view.word is None
            assert not mentions(view.model_dump_json(), word)


@settings(max_examples=150, deadline=None)
@given(played=played_games())
def test_views_never_contain_another_seats_reasoning(played: PlayedGame) -> None:
    for view in played.views:
        seats = {int(seat) for seat in MARKER_PATTERN.findall(view.model_dump_json())}

        assert seats <= {view.seat}
        assert all(
            MARKER_PATTERN.search(entry.private_reasoning) for entry in view.scratchpad
        )


@settings(max_examples=150, deadline=None)
@given(played=played_games())
def test_views_contain_no_votes_before_they_are_revealed(played: PlayedGame) -> None:
    for view in played.views:
        if view.phase in (GamePhase.CLUE, GamePhase.DISCUSSION, GamePhase.VOTE):
            assert view.vote_result is None
            assert all(entry.phase is not GamePhase.VOTE for entry in view.scratchpad)
            assert "voted for" not in view.model_dump_json()


@settings(max_examples=150, deadline=None)
@given(played=played_games())
def test_public_projection_has_no_private_fields(played: PlayedGame) -> None:
    word = played.game.secret.word
    outcome_seq = played.game.events_of_type(OutcomeEvent)[0].seq

    for event in played.game.events:
        projection = public_projection(event)

        if event.visibility is EventVisibility.PRIVATE:
            assert projection is None
            continue

        assert projection is not None
        assert not event.private_fields & projection.keys()

        text = str(projection)

        assert MARKER_PATTERN.search(text) is None

        if event.seq < outcome_seq:
            assert not mentions(text, word)
