"""Scripted replays of notable real games, documented in `docs/plans/playtests.md`."""

from imposter.config import (
    GameConfig,
    GameOutcome,
    GamePhase,
    PlayerConfig,
    PlayerRole,
    SecretWord,
)
from imposter.engine.events import (
    ClueGivenEvent,
    PlayerErrorEvent,
    ReflectionEvent,
    SecretWordSaidEvent,
    public_projection,
)
from imposter.engine.game import Game
from imposter.orchestration.runner import GameRunner
from imposter.players.base import ClueResponse, DebriefResponse
from imposter.players.fake import ScriptedPlayer
from imposter.players.prompt import PlayerPromptRenderer


def lighthouse_game() -> Game:
    """Set up playtest 1: the seats, roles and word of the real game."""
    config = GameConfig(
        players=[
            PlayerConfig(model_id="gemini-flash", model_display_name="Gemini Flash"),
            PlayerConfig(model_id="claude-haiku", model_display_name="Claude Haiku"),
            PlayerConfig(model_id="gpt-oss", model_display_name="GPT-OSS 120B"),
            PlayerConfig(
                model_id="gemini-flash-lite", model_display_name="Gemini Flash-Lite"
            ),
        ],
        public_category=True,
        seed=42,
    )

    return Game.create(
        config=config, secret=SecretWord(word="lighthouse", category="places")
    )


def test_lighthouse_game_has_the_seats_of_the_real_game() -> None:
    game = lighthouse_game()

    assert [(s.name, s.player.model_id, s.role) for s in game.seats] == [
        ("Alice", "gpt-oss", PlayerRole.CIVILIAN),
        ("Bob", "claude-haiku", PlayerRole.IMPOSTER),
        ("Charlie", "gemini-flash-lite", PlayerRole.CIVILIAN),
        ("Dave", "gemini-flash", PlayerRole.CIVILIAN),
    ]


async def test_lighthouse_imposter_saying_the_word_as_a_clue_loses_at_once() -> None:
    game = lighthouse_game()
    reflection = DebriefResponse(reflection="Reflection.")
    players = [
        ScriptedPlayer(script=[ClueResponse(clue="beacon"), reflection]),
        ScriptedPlayer(
            script=[
                ClueResponse(
                    clue="lighthouse",
                    private_reasoning=(
                        'Alice said "beacon", which suggests a coastal or navigation '
                        'place. "lighthouse" is a plausible fit.'
                    ),
                ),
                reflection,
            ]
        ),
        ScriptedPlayer(script=[reflection]),
        ScriptedPlayer(script=[reflection]),
    ]

    await GameRunner(players=players).play(game)

    said = game.events_of_type(SecretWordSaidEvent)

    assert game.outcome is GameOutcome.IMPOSTER_SAID_WORD
    assert [event.seat for event in said] == [1]
    assert "lighthouse" not in str(public_projection(said[0]))
    assert [event.clue for event in game.events_of_type(ClueGivenEvent)] == ["beacon"]
    assert game.events_of_type(PlayerErrorEvent) == []
    assert len(game.events_of_type(ReflectionEvent)) == 4
    assert game.phase is GamePhase.DONE
    assert all(not player.script for player in players)


def test_lighthouse_prompts_carry_the_word_and_repeat_rules() -> None:
    game = lighthouse_game()
    renderer = PlayerPromptRenderer()
    game.start_turn(0)
    game.submit_clue(seat=0, clue="beacon", private_reasoning="")
    imposter_view = game.view_for(1)

    instruction = renderer.instruction(imposter_view)
    task = renderer.task(view=imposter_view)

    assert "**Never say the secret word.**" in instruction
    assert "**Never repeat a clue.**" in instruction
    assert "Give a clue that is related to it instead" in instruction
    assert "you must not repeat (this includes your own): beacon." in task
    assert "lighthouse" not in instruction + task
