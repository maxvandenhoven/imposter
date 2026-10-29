import asyncio
from typing import Any

import pytest

from imposter.config import (
    GameConfig,
    GameOutcome,
    GamePhase,
    IdentityMode,
    PlayerRole,
    SecretWord,
)
from imposter.engine.events import (
    ClueGivenEvent,
    GuessMadeEvent,
    PlayerErrorEvent,
    VoteCastEvent,
)
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.judge.base import JudgeVerdict
from imposter.orchestration.runner import GameRunner
from imposter.players.base import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PlayerResponse,
    TurnUsage,
    VoteResponse,
)
from imposter.players.fake import RandomPlayer, ScriptedPlayer, ScriptStep

WORD = "giraffe"


class RecordingJudge:
    """A judge that accepts every guess and every clue not starting with `bad`.

    Attributes:
        judged: The candidates the judge was asked about, with the word.
    """

    def __init__(self) -> None:
        self.judged: list[tuple[str, str]] = []

    def verdict(self, *, candidate: str, word: str) -> JudgeVerdict:
        """Record a question and answer it."""
        self.judged.append((candidate, word))

        return JudgeVerdict(
            verdict=not candidate.startswith("bad"),
            confidence=1.0,
            rationale="Scripted.",
            judge_model="fake",
        )

    async def is_same_word(self, guess: str, word: str) -> JudgeVerdict:
        return self.verdict(candidate=guess, word=word)

    async def is_valid_clue(self, clue: str, word: str) -> JudgeVerdict:
        return self.verdict(candidate=clue, word=word)


def new_game(*, player_count: int = 4, **options: Any) -> Game:
    """Create a seeded game with `player_count` seats."""
    config = GameConfig.model_validate(
        {
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

    return Game.create(config=config, secret=SecretWord(word=WORD, category="animals"))


def script_for(game: Game, seat: int, *, guess: str = "zebra") -> list[ScriptStep]:
    """Script a whole valid game for a seat.

    Every civilian votes for the first imposter and every imposter for the first
    civilian, so the first imposter is always caught.
    """
    config = game.config
    first_imposter = game.imposters[0]
    first_civilian = next(s.seat for s in game.seats if s.role is PlayerRole.CIVILIAN)
    is_imposter = game.seats[seat].role is PlayerRole.IMPOSTER
    target = first_civilian if is_imposter else first_imposter
    steps: list[ScriptStep] = [
        ClueResponse(clue=f"clue{round_}x{seat}", private_reasoning=f"clue {round_}")
        for round_ in range(1, config.clue_rounds + 1)
    ]
    steps += [
        DiscussionResponse(statement=f"Round {round_} from {seat}.", private_reasoning="")
        for round_ in range(1, config.discussion_rounds + 1)
    ]
    steps.append(VoteResponse(vote_for=game.seats[target].name, private_reasoning="vote"))

    if is_imposter:
        steps.append(GuessResponse(guess=guess, private_reasoning="guess"))

    steps.append(DebriefResponse(reflection="Good game."))

    return steps


def scripted_players(game: Game, **options: Any) -> list[ScriptedPlayer]:
    """Build a scripted player with a whole valid game for every seat, in seat order."""
    return [
        ScriptedPlayer(script=script_for(game, seat.seat, **options))
        for seat in game.seats
    ]


def errors(game: Game) -> list[str]:
    """List the messages of all player errors."""
    return [event.message for event in game.events_of_type(PlayerErrorEvent)]


@pytest.mark.parametrize("identity_mode", list(IdentityMode))
@pytest.mark.parametrize("player_count", range(3, 9))
async def test_scripted_games_play_to_the_end(
    identity_mode: IdentityMode, player_count: int
) -> None:
    game = new_game(
        player_count=player_count,
        identity_mode=identity_mode,
        imposter_count=(player_count - 1) // 2,
    )
    players = scripted_players(game)

    await GameRunner(players=players).play(game)

    assert game.phase is GamePhase.DONE
    assert errors(game) == []
    assert all(not player.script for player in players)
    expected = (
        GameOutcome.CIVILIANS_WIN
        if len(game.imposters) == 1
        else (GameOutcome.IMPOSTER_WINS)
    )
    assert game.outcome is expected


async def test_caught_imposter_steals_with_exact_guess() -> None:
    game = new_game()

    await GameRunner(players=scripted_players(game, guess="Giraffes")).play(game)

    assert game.outcome is GameOutcome.IMPOSTER_STEALS


async def test_guess_judge_decides_inexact_guesses_only() -> None:
    judge = RecordingJudge()
    game = new_game()
    await GameRunner(
        players=scripted_players(game, guess="camelopard"), judge=judge
    ).play(game)

    assert judge.judged[-1:] == [("camelopard", WORD)]
    assert game.events_of_type(GuessMadeEvent)[0].judged_by == "judge"
    assert game.outcome is GameOutcome.IMPOSTER_STEALS


async def test_invalid_clue_is_retried_with_the_reason() -> None:
    game = new_game()
    players = scripted_players(game)
    civilian = next(s.seat for s in game.seats if s.role is PlayerRole.CIVILIAN)
    players[civilian].script.insert(0, ClueResponse(clue="long neck"))

    await GameRunner(players=players).play(game)

    retry_reasons = players[civilian].retry_reasons[:2]

    assert retry_reasons == [None, "the clue must be exactly one word"]
    assert game.phase is GamePhase.DONE


async def test_second_invalid_clue_becomes_a_pass() -> None:
    game = new_game()
    players = scripted_players(game)
    civilian = next(s.seat for s in game.seats if s.role is PlayerRole.CIVILIAN)
    players[civilian].script[0:1] = [
        ClueResponse(clue="long neck", private_reasoning="oops"),
        ClueResponse(clue="two words"),
    ]

    await GameRunner(players=players).play(game)

    clue = next(
        e for e in game.events if isinstance(e, ClueGivenEvent) and e.seat == civilian
    )

    assert clue.clue is None
    assert clue.rejection_reason == "the clue must be exactly one word"
    assert errors(game) == [
        "invalid action, falling back: the clue must be exactly one word"
    ]


async def test_saying_the_word_ends_the_game_without_a_retry_or_judge() -> None:
    judge = RecordingJudge()
    game = new_game(clue_rounds=1, discussion_rounds=0)
    speaker = game.pending_seats[0]
    players = [
        ScriptedPlayer(script=[DebriefResponse(reflection="Over already.")])
        for _ in game.seats
    ]
    players[speaker].script.insert(0, ClueResponse(clue=WORD))

    await GameRunner(players=players, judge=judge).play(game)

    expected = (
        GameOutcome.IMPOSTER_SAID_WORD
        if speaker in game.imposters
        else GameOutcome.CIVILIAN_SAID_WORD
    )
    assert game.outcome is expected
    assert judge.judged == []
    assert players[speaker].retry_reasons == [None, None]
    assert errors(game) == []
    assert game.phase is GamePhase.DONE


async def test_clue_judge_rejection_is_retried_for_civilians_only() -> None:
    judge = RecordingJudge()
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    imposter = game.imposters[0]
    civilian = next(s.seat for s in game.seats if s.role is PlayerRole.CIVILIAN)
    players[imposter].script[0] = ClueResponse(clue="badclue")
    players[civilian].script.insert(0, ClueResponse(clue="badclue"))

    await GameRunner(players=players, judge=judge).play(game)

    assert (
        players[civilian].retry_reasons[1] == "the clue is too close to the secret word"
    )
    assert all(reason is None for reason in players[imposter].retry_reasons)


async def test_model_clue_check_can_be_turned_off() -> None:
    judge = RecordingJudge()
    game = new_game(clue_rounds=1, discussion_rounds=0, model_clue_check=False)
    players = scripted_players(game)
    civilian = next(s.seat for s in game.seats if s.role is PlayerRole.CIVILIAN)
    players[civilian].script.insert(0, ClueResponse(clue="giraffid"))

    await GameRunner(players=players, judge=judge).play(game)

    # The code checks still reject the shared stem, and only the guess is judged.
    assert players[civilian].retry_reasons[1] == (
        "the clue is too close to the secret word"
    )
    assert judge.judged == [("zebra", WORD)]


async def test_invalid_vote_falls_back_to_an_abstention() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    seat = game.imposters[0]
    vote_index = next(
        i for i, step in enumerate(players[seat].script) if isinstance(step, VoteResponse)
    )
    players[seat].script[vote_index : vote_index + 1] = [
        VoteResponse(vote_for=game.seats[seat].name),
        VoteResponse(vote_for="Nobody"),
    ]

    await GameRunner(players=players).play(game)

    revealed = next(e for e in game.events if e.model_dump()["type"] == "votes_revealed")

    assert revealed.model_dump()["votes"][seat]["target"] is None
    assert len(errors(game)) == 1


async def test_failing_player_gets_the_phase_fallback() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=1)
    players = scripted_players(game)
    players[0].script[1] = RuntimeError("model unavailable")

    await GameRunner(players=players).play(game)

    assert errors(game) == ["player failed: model unavailable"]
    assert game.view_for(0).statements[0].statement == ""
    assert game.phase is GamePhase.DONE


async def test_failing_guess_and_debrief_fall_back_to_empty_answers() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    imposter = game.imposters[0]
    players[imposter].script[-2:] = [RuntimeError("down"), RuntimeError("still down")]

    await GameRunner(players=players).play(game)

    reveal = game.view_for(imposter).reveal

    assert reveal is not None
    assert reveal.guesses[0].guess == ""
    assert game.outcome is GameOutcome.CIVILIANS_WIN
    assert len(errors(game)) == 2
    assert game.phase is GamePhase.DONE


async def test_wrong_response_type_is_retried() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    players[0].script.insert(0, DebriefResponse(reflection="too early"))

    await GameRunner(players=players).play(game)

    assert players[0].retry_reasons[1] == "expected a response for the clue phase"


async def test_player_reported_errors_and_usage_are_recorded() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    usage = TurnUsage(model_id="model-0", input_tokens=10, output_tokens=2)
    players[0].script[0] = PlayerResponse(
        output=ClueResponse(clue="fallbackclue"), usage=usage, error="bad json"
    )

    await GameRunner(players=players).play(game)

    assert errors(game) == ["bad json"]
    assert game.tokens_used == 12


async def test_player_that_gives_up_gets_the_fallback_with_its_usage() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    usage = TurnUsage(model_id="model-0", input_tokens=10, output_tokens=2)
    players[0].script[0] = PlayerResponse(output=None, usage=usage, error="invalid json")

    await GameRunner(players=players).play(game)

    assert errors(game) == ["invalid json"]
    assert game.view_for(0).clues[0].clue is None
    assert players[0].retry_reasons[0] is None
    assert game.tokens_used == 12
    assert game.phase is GamePhase.DONE


async def test_token_budget_aborts_the_game() -> None:
    game = new_game(token_budget=50)
    usage = TurnUsage(model_id="model", input_tokens=20)
    players = [RandomPlayer(seed=seat.seat, usage=usage) for seat in game.seats]

    await GameRunner(players=players).play(game)

    assert game.phase is GamePhase.ABORTED
    assert game.tokens_used == 60


async def test_budget_abort_during_a_parallel_phase_stops_cleanly() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0, token_budget=10)
    players = scripted_players(game)
    usage = TurnUsage(model_id="model", input_tokens=20)

    for player in players:
        player.script = [
            step
            if not isinstance(step, VoteResponse)
            else PlayerResponse(output=step, usage=usage)
            for step in player.script
        ]

    await GameRunner(players=players).play(game)

    assert game.phase is GamePhase.ABORTED
    assert game.tokens_used == 20 * len(game.seats)


@pytest.mark.parametrize("seed", range(5))
async def test_random_players_finish_games_despite_blunders(seed: int) -> None:
    game = new_game(player_count=6, imposter_count=2, seed=seed)
    players = [
        RandomPlayer(seed=seed * 10 + seat.seat, blunder_rate=0.4) for seat in game.seats
    ]

    await GameRunner(players=players).play(game)

    assert game.phase is GamePhase.DONE
    assert game.outcome is not None


async def test_asking_a_player_does_not_change_the_game() -> None:
    game = new_game()
    game.start_turn(0)
    player = ScriptedPlayer(script=[ClueResponse(clue="tall", private_reasoning="hm")])
    runner = GameRunner(players=[player])
    events_before = game.events

    result = await runner.ask(game=game, seat=0)

    assert result.output == ClueResponse(clue="tall", private_reasoning="hm")
    assert game.events == events_before

    runner.apply(game=game, result=result)

    assert game.events_of_type(ClueGivenEvent)[0].clue == "tall"


class SlowPlayer:
    """A scripted player that answers after a delay, to reorder parallel answers.

    Attributes:
        player: The scripted player that gives the answers.
        delay: The seconds to wait before every answer.
    """

    def __init__(self, *, player: ScriptedPlayer, delay: float) -> None:
        """Initialize the player.

        Args:
            player: The scripted player that gives the answers.
            delay: The seconds to wait before every answer.
        """
        self.player = player
        self.delay = delay

    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse:
        """Wait, then give the next scripted answer.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt was rejected, if any.

        Returns:
            The next scripted response.
        """
        await asyncio.sleep(self.delay)

        return await self.player.take_turn(view=view, retry_reason=retry_reason)


async def test_parallel_answers_are_applied_in_seat_order() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = [
        SlowPlayer(player=player, delay=0.01 * (len(game.seats) - seat))
        for seat, player in enumerate(scripted_players(game))
    ]

    await GameRunner(players=players).play(game)

    assert [event.seat for event in game.events_of_type(VoteCastEvent)] == [0, 1, 2, 3]
