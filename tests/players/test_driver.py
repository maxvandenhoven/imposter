from typing import Any

import pytest

from imposter.engine.config import (
    GameConfig,
    GameOutcome,
    GamePhase,
    IdentityMode,
    PlayerRole,
    SecretWord,
)
from imposter.engine.events import ClueGivenEvent, GuessJudgedEvent, PlayerErrorEvent
from imposter.engine.state import GameState
from imposter.players.base import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PlayerResponse,
    TurnUsage,
    VoteResponse,
)
from imposter.players.driver import GameDriver
from imposter.players.fake import RandomPlayer, ScriptedPlayer, ScriptStep

WORD = "giraffe"


def new_game(*, player_count: int = 4, **options: Any) -> GameState:
    """Create a seeded game with `player_count` seats."""
    config = GameConfig.model_validate(
        {
            "category": "animals",
            "players": [
                {
                    "model_id": f"model-{seat % 2}",
                    "model_display_name": f"Model {seat % 2}",
                }
                for seat in range(player_count)
            ],
            "seed": 11,
            **options,
        }
    )

    return GameState.create(
        config=config, secret=SecretWord(word=WORD, category="animals")
    )


def script_for(state: GameState, seat: int, *, guess: str = "zebra") -> list[ScriptStep]:
    """Script a whole valid game for a seat.

    Every civilian votes for the first imposter and every imposter for the first
    civilian, so the first imposter is always caught.
    """
    config = state.config
    first_imposter = state.imposters[0]
    first_civilian = next(s.seat for s in state.seats if s.role is PlayerRole.CIVILIAN)
    is_imposter = state.seats[seat].role is PlayerRole.IMPOSTER
    target = first_civilian if is_imposter else first_imposter
    steps: list[ScriptStep] = [
        ClueResponse(clue=f"clue{round_}x{seat}", private_reasoning=f"clue {round_}")
        for round_ in range(1, config.clue_rounds + 1)
    ]
    steps += [
        DiscussionResponse(statement=f"Round {round_} from {seat}.", private_reasoning="")
        for round_ in range(1, config.discussion_rounds + 1)
    ]
    steps.append(
        VoteResponse(vote_for=state.seats[target].name, private_reasoning="vote")
    )

    if is_imposter:
        steps.append(GuessResponse(guess=guess, private_reasoning="guess"))

    steps.append(DebriefResponse(reflection="Good game."))

    return steps


def scripted_players(state: GameState, **options: Any) -> dict[int, ScriptedPlayer]:
    """Build a scripted player with a whole valid game for every seat."""
    return {
        seat.seat: ScriptedPlayer(
            seat=seat.seat, script=script_for(state, seat.seat, **options)
        )
        for seat in state.seats
    }


def errors(state: GameState) -> list[str]:
    """List the messages of all player errors."""
    return [
        event.message for event in state.events if isinstance(event, PlayerErrorEvent)
    ]


@pytest.mark.parametrize("identity_mode", list(IdentityMode))
@pytest.mark.parametrize("player_count", range(3, 9))
async def test_scripted_games_play_to_the_end(
    identity_mode: IdentityMode, player_count: int
) -> None:
    state = new_game(
        player_count=player_count,
        identity_mode=identity_mode,
        imposter_count=(player_count - 1) // 2,
    )
    players = scripted_players(state)

    await GameDriver(state=state, players=players).run()

    assert state.phase is GamePhase.DONE
    assert errors(state) == []
    assert all(not player.script for player in players.values())
    expected = (
        GameOutcome.CIVILIANS_WIN
        if len(state.imposters) == 1
        else (GameOutcome.IMPOSTER_WINS)
    )
    assert state.outcome is expected


async def test_caught_imposter_steals_with_exact_guess() -> None:
    state = new_game()

    await GameDriver(state=state, players=scripted_players(state, guess="Giraffes")).run()

    assert state.outcome is GameOutcome.IMPOSTER_STEALS


async def test_guess_judge_decides_inexact_guesses_only() -> None:
    judged: list[tuple[str, str]] = []

    async def judge(guess: str, word: str) -> bool:
        judged.append((guess, word))
        return True

    state = new_game()
    await GameDriver(
        state=state,
        players=scripted_players(state, guess="camelopard"),
        guess_judge=judge,
    ).run()

    verdict = next(e for e in state.events if isinstance(e, GuessJudgedEvent))

    assert judged == [("camelopard", WORD)]
    assert verdict.method == "judge"
    assert state.outcome is GameOutcome.IMPOSTER_STEALS


async def test_invalid_clue_is_retried_with_the_reason() -> None:
    state = new_game()
    players = scripted_players(state)
    civilian = next(s.seat for s in state.seats if s.role is PlayerRole.CIVILIAN)
    players[civilian].script.insert(0, ClueResponse(clue="long neck"))

    await GameDriver(state=state, players=players).run()

    retry_reasons = [task.retry_reason for task in players[civilian].tasks[:2]]

    assert retry_reasons == [None, "the clue must be exactly one word"]
    assert state.phase is GamePhase.DONE


async def test_second_invalid_clue_becomes_a_pass() -> None:
    state = new_game()
    players = scripted_players(state)
    civilian = next(s.seat for s in state.seats if s.role is PlayerRole.CIVILIAN)
    players[civilian].script[0:1] = [
        ClueResponse(clue=WORD, private_reasoning="oops"),
        ClueResponse(clue="two words"),
    ]

    await GameDriver(state=state, players=players).run()

    clue = next(
        e for e in state.events if isinstance(e, ClueGivenEvent) and e.seat == civilian
    )

    assert clue.clue is None
    assert clue.rejection_reason == "the clue must be exactly one word"
    assert errors(state) == [
        "invalid action, falling back: the clue must be exactly one word"
    ]


async def test_imposter_saying_the_word_passes_without_a_retry() -> None:
    state = new_game()
    players = scripted_players(state)
    imposter = state.imposters[0]
    players[imposter].script[0] = ClueResponse(clue=WORD)

    await GameDriver(state=state, players=players).run()

    clue = next(
        e for e in state.events if isinstance(e, ClueGivenEvent) and e.seat == imposter
    )

    assert clue.clue is None
    assert all(task.retry_reason is None for task in players[imposter].tasks)
    assert state.phase is GamePhase.DONE


async def test_clue_judge_rejection_is_retried_for_civilians_only() -> None:
    async def judge(clue: str, word: str) -> bool:
        return not clue.startswith("bad")

    state = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(state)
    imposter = state.imposters[0]
    civilian = next(s.seat for s in state.seats if s.role is PlayerRole.CIVILIAN)
    players[imposter].script[0] = ClueResponse(clue="badclue")
    players[civilian].script.insert(0, ClueResponse(clue="badclue"))

    await GameDriver(state=state, players=players, clue_judge=judge).run()

    assert (
        players[civilian].tasks[1].retry_reason
        == "the clue is too close to the secret word"
    )
    assert all(task.retry_reason is None for task in players[imposter].tasks)


async def test_invalid_vote_falls_back_to_an_abstention() -> None:
    state = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(state)
    seat = state.imposters[0]
    vote_index = next(
        i for i, step in enumerate(players[seat].script) if isinstance(step, VoteResponse)
    )
    players[seat].script[vote_index : vote_index + 1] = [
        VoteResponse(vote_for=state.seats[seat].name),
        VoteResponse(vote_for="Nobody"),
    ]

    await GameDriver(state=state, players=players).run()

    revealed = next(e for e in state.events if e.model_dump()["type"] == "votes_revealed")

    assert revealed.model_dump()["votes"][seat]["target"] is None
    assert len(errors(state)) == 1


async def test_failing_player_gets_the_phase_fallback() -> None:
    state = new_game(clue_rounds=1, discussion_rounds=1)
    players = scripted_players(state)
    players[0].script[1] = RuntimeError("model unavailable")

    await GameDriver(state=state, players=players).run()

    assert errors(state) == ["player failed: model unavailable"]
    assert state.view_for(0).statements[0].statement == ""
    assert state.phase is GamePhase.DONE


async def test_failing_guess_and_debrief_fall_back_to_empty_answers() -> None:
    state = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(state)
    imposter = state.imposters[0]
    players[imposter].script[-2:] = [RuntimeError("down"), RuntimeError("still down")]

    await GameDriver(state=state, players=players).run()

    reveal = state.view_for(imposter).reveal

    assert reveal is not None
    assert reveal.guesses[0].guess == ""
    assert state.outcome is GameOutcome.CIVILIANS_WIN
    assert len(errors(state)) == 2
    assert state.phase is GamePhase.DONE


async def test_wrong_response_type_is_retried() -> None:
    state = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(state)
    players[0].script.insert(0, DebriefResponse(reflection="too early"))

    await GameDriver(state=state, players=players).run()

    assert players[0].tasks[1].retry_reason == "expected a response for the clue phase"


async def test_player_reported_errors_and_usage_are_recorded() -> None:
    state = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(state)
    usage = TurnUsage(model_id="model-0", input_tokens=10, output_tokens=2)
    players[0].script[0] = PlayerResponse(
        output=ClueResponse(clue="fallbackclue"),
        usage=usage,
        attempts=2,
        error="bad json",
    )

    await GameDriver(state=state, players=players).run()

    assert errors(state) == ["bad json"]
    assert state.tokens_used == 12


async def test_token_budget_aborts_the_game() -> None:
    state = new_game(token_budget=50)
    usage = TurnUsage(model_id="model", input_tokens=20)
    players = {
        seat.seat: RandomPlayer(seat=seat.seat, seed=seat.seat, usage=usage)
        for seat in state.seats
    }

    await GameDriver(state=state, players=players).run()

    assert state.phase is GamePhase.ABORTED
    assert state.tokens_used == 60


async def test_budget_abort_during_a_parallel_phase_stops_cleanly() -> None:
    state = new_game(clue_rounds=1, discussion_rounds=0, token_budget=10)
    players = scripted_players(state)
    usage = TurnUsage(model_id="model", input_tokens=20)

    for player in players.values():
        player.script = [
            step
            if not isinstance(step, VoteResponse)
            else PlayerResponse(output=step, usage=usage)
            for step in player.script
        ]

    await GameDriver(state=state, players=players).run()

    assert state.phase is GamePhase.ABORTED
    assert state.tokens_used == 20 * len(state.seats)


@pytest.mark.parametrize("seed", range(5))
async def test_random_players_finish_games_despite_blunders(seed: int) -> None:
    state = new_game(player_count=6, imposter_count=2, seed=seed)
    players = {
        seat.seat: RandomPlayer(
            seat=seat.seat, seed=seed * 10 + seat.seat, blunder_rate=0.4
        )
        for seat in state.seats
    }

    await GameDriver(state=state, players=players).run()

    assert state.phase is GamePhase.DONE
    assert state.outcome is not None
