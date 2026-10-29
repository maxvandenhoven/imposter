"""Snapshot tests of the rendered player prompts.

Run with `UPDATE_SNAPSHOTS=1` to rewrite the snapshots after a deliberate prompt change,
then review the diff of `tests/players/snapshots/`.
"""

import asyncio
import os
from pathlib import Path

import pytest

from imposter.config import GameConfig, GamePhase, PlayerConfig, PlayerRole, SecretWord
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.orchestration.runner import GameRunner
from imposter.players.fake import RandomPlayer
from imposter.players.prompt import PlayerPromptRenderer

SNAPSHOT_DIR = Path(__file__).with_name("snapshots")

SNAPSHOT_CASES = [
    (GamePhase.CLUE, PlayerRole.CIVILIAN),
    (GamePhase.CLUE, PlayerRole.IMPOSTER),
    (GamePhase.DISCUSSION, PlayerRole.CIVILIAN),
    (GamePhase.DISCUSSION, PlayerRole.IMPOSTER),
    (GamePhase.VOTE, PlayerRole.CIVILIAN),
    (GamePhase.VOTE, PlayerRole.IMPOSTER),
    (GamePhase.GUESS, PlayerRole.IMPOSTER),
    (GamePhase.DEBRIEF, PlayerRole.CIVILIAN),
    (GamePhase.DEBRIEF, PlayerRole.IMPOSTER),
]


def collect_views(game: Game) -> dict[tuple[GamePhase, PlayerRole], PlayerView]:
    """Play a game with random players and keep the last view of each phase and role."""
    runner = GameRunner(players=[RandomPlayer(seed=seat.seat) for seat in game.seats])
    views: dict[tuple[GamePhase, PlayerRole], PlayerView] = {}

    async def play() -> None:
        while not game.is_over:
            for seat in game.pending_seats:
                view = game.view_for(seat)
                views[(view.phase, view.role)] = view

            await runner.play_step(game)

    asyncio.run(play())

    return views


@pytest.fixture(scope="module")
def views() -> dict[tuple[GamePhase, PlayerRole], PlayerView]:
    """Return views of a seeded five player game with a hint, in every phase."""
    config = GameConfig(
        players=[PlayerConfig(model_id="m")] * 5,
        imposter_hint=True,
        clue_rounds=2,
        discussion_rounds=1,
        seed=5,
    )
    secret = SecretWord(word="giraffe", category="animals", hint="savanna")

    return collect_views(Game.create(config=config, secret=secret))


@pytest.fixture(scope="module")
def renderer() -> PlayerPromptRenderer:
    """Return the renderer with the built-in templates."""
    return PlayerPromptRenderer()


def check_snapshot(name: str, text: str) -> None:
    """Compare a text with its snapshot file, or rewrite it with `UPDATE_SNAPSHOTS=1`."""
    path = SNAPSHOT_DIR / f"{name}.md"

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(exist_ok=True)
        path.write_text(text + "\n")

    assert text + "\n" == path.read_text()


@pytest.mark.parametrize(("phase", "role"), SNAPSHOT_CASES)
def test_prompt_matches_snapshot(
    views: dict[tuple[GamePhase, PlayerRole], PlayerView],
    renderer: PlayerPromptRenderer,
    phase: GamePhase,
    role: PlayerRole,
) -> None:
    view = views[(phase, role)]
    text = renderer.instruction(view) + "\n\n---\n\n" + renderer.task(view=view)

    check_snapshot(name=f"{phase}_{role}", text=text)


def test_task_with_retry_reason_and_schema_matches_snapshot(
    views: dict[tuple[GamePhase, PlayerRole], PlayerView], renderer: PlayerPromptRenderer
) -> None:
    view = views[(GamePhase.VOTE, PlayerRole.CIVILIAN)]
    text = renderer.task(
        view=view, retry_reason='"Zed" is not a player', include_schema=True
    )

    check_snapshot(name="vote_task_with_schema", text=text)


def test_rules_adapt_to_imposter_count_and_discussion_rounds(
    renderer: PlayerPromptRenderer,
) -> None:
    config = GameConfig(
        players=[PlayerConfig(model_id="m")] * 6,
        imposter_count=2,
        discussion_rounds=0,
        clue_rounds=1,
        seed=1,
    )
    game = Game.create(config=config, secret=SecretWord(word="giraffe"))
    instruction = renderer.instruction(game.view_for(game.imposters[0]))

    assert "Every player except 2 knows the same secret word." in instruction
    assert "Discussion:" not in instruction
    assert "there is 1 round" in instruction
    assert "2. Vote:" in instruction
    assert "an imposter. You do not know the secret word." in instruction


def test_task_rejects_phases_without_actions(renderer: PlayerPromptRenderer) -> None:
    config = GameConfig(players=[PlayerConfig(model_id="m")] * 3, seed=1)
    view = Game.create(config=config, secret=SecretWord(word="giraffe")).view_for(0)

    with pytest.raises(ValueError, match="do not act in phase resolution"):
        renderer.task(view=view.model_copy(update={"phase": GamePhase.RESOLUTION}))
