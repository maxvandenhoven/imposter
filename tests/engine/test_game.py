from typing import Any

import pytest

from imposter.config import (
    GameConfig,
    GameOutcome,
    GamePhase,
    IdentityMode,
    PlayerConfig,
    PlayerRole,
    SecretWord,
)
from imposter.engine.events import (
    ClueGivenEvent,
    GameAbortedEvent,
    GameFinishedEvent,
    GameStartedEvent,
    GuessMadeEvent,
    OutcomeEvent,
    PhaseStartedEvent,
    StatementMadeEvent,
    VotesRevealedEvent,
)
from imposter.engine.game import Game, InvalidActionError
from imposter.engine.views import other_players
from imposter.utils.text import REDACTION

WORD = "giraffe"


def new_game(*, player_count: int = 4, hint: str | None = None, **options: Any) -> Game:
    """Create a seeded game with `player_count` seats in the first clue round."""
    config = GameConfig.model_validate(
        {
            "players": [{"model_id": f"model-{seat}"} for seat in range(player_count)],
            "seed": 7,
            **options,
        }
    )

    return Game.create(
        config=config, secret=SecretWord(word=WORD, category="animals", hint=hint)
    )


def give_clue(game: Game, *, seat: int, clue: str | None, reasoning: str = "") -> None:
    """Start the seat's turn and submit a clue."""
    game.start_turn(seat)
    game.submit_clue(seat=seat, clue=clue, private_reasoning=reasoning)


def play_until_vote(game: Game) -> None:
    """Play every clue and discussion turn with distinct, valid actions."""
    while game.phase in (GamePhase.CLUE, GamePhase.DISCUSSION):
        seat = game.pending_seats[0]

        if game.phase is GamePhase.CLUE:
            give_clue(game, seat=seat, clue=f"clue{game.round}x{seat}")
        else:
            game.start_turn(seat)
            game.submit_statement(seat=seat, statement="Hello.", private_reasoning="")


def vote(game: Game, targets: dict[int, int | None]) -> None:
    """Cast every vote, by seat, with `None` as an abstention."""
    for voter in game.pending_seats:
        game.start_turn(voter)

    for voter, target in targets.items():
        name = None if target is None else game.seats[target].name
        game.submit_vote(voter=voter, vote_for=name, private_reasoning="")


def guess_all(game: Game, guesses: dict[int, str]) -> None:
    """Let every imposter guess in turn."""
    for seat in game.imposters:
        game.start_turn(seat)
        game.submit_guess(
            seat=seat, guess=guesses.get(seat, "wrong"), private_reasoning=""
        )


def votes_against(game: Game, targets: list[int]) -> dict[int, int | None]:
    """Have every seat vote for the first target that is not itself."""
    return {
        voter: next(target for target in targets if target != voter)
        for voter in range(len(game.seats))
    }


class TestCreate:
    def test_new_game_starts_in_the_first_clue_round(self) -> None:
        game = new_game()

        assert [type(event) for event in game.events] == [
            GameStartedEvent,
            PhaseStartedEvent,
        ]
        assert (game.phase, game.round) == (GamePhase.CLUE, 1)
        assert game.pending_seats == [0, 1, 2, 3]

    def test_game_started_records_the_imposters_privately(self) -> None:
        game = new_game()
        started = game.events_of_type(GameStartedEvent)[0]

        assert started.imposters == game.imposters
        assert "imposters" in started.private_fields

    def test_seed_fixes_seats_roles_and_names(self) -> None:
        first, second = new_game(player_count=8), new_game(player_count=8)

        assert first.seats == second.seats
        assert first.game_id != second.game_id

    def test_roles_have_the_configured_number_of_imposters(self) -> None:
        game = new_game(player_count=8, imposter_count=3)

        assert len(game.imposters) == 3
        assert sum(seat.role is PlayerRole.CIVILIAN for seat in game.seats) == 5

    def test_enabled_hint_must_exist(self) -> None:
        with pytest.raises(ValueError, match="no hint"):
            new_game(imposter_hint=True)

    def test_hint_must_differ_from_word(self) -> None:
        with pytest.raises(ValueError, match="differ"):
            new_game(imposter_hint=True, hint="Giraffes")

    def test_models_identity_uses_display_names(self) -> None:
        config = GameConfig(
            players=[PlayerConfig(model_id="m", model_display_name="Gemini Flash")] * 3,
            identity_mode=IdentityMode.MODELS,
        )
        game = Game.create(config=config, secret=SecretWord(word=WORD))

        assert sorted(seat.name for seat in game.seats) == [
            "Gemini Flash #1",
            "Gemini Flash #2",
            "Gemini Flash #3",
        ]


class TestTurns:
    def test_sequential_phase_only_starts_the_next_seat(self) -> None:
        with pytest.raises(InvalidActionError, match="turn of seat 0"):
            new_game().start_turn(1)

    def test_turn_cannot_start_twice(self) -> None:
        game = new_game()
        game.start_turn(0)

        with pytest.raises(InvalidActionError, match="no turn to start"):
            game.start_turn(0)

    def test_action_needs_a_started_turn(self) -> None:
        with pytest.raises(InvalidActionError, match="no started turn"):
            new_game().submit_clue(seat=0, clue="tall", private_reasoning="")

    def test_action_must_match_the_phase(self) -> None:
        game = new_game()
        game.start_turn(0)

        with pytest.raises(InvalidActionError, match="Cannot act in phase discussion"):
            game.submit_statement(seat=0, statement="Hi.", private_reasoning="")


class TestClues:
    @pytest.mark.parametrize(
        ("clue", "reason"),
        [
            ("long neck", "exactly one word"),
            ("", "exactly one word"),
            ("Giraffes", "must not be or contain"),
            ("babygiraffe", "must not be or contain"),
        ],
    )
    def test_code_checks_reject_invalid_clues(self, clue: str, reason: str) -> None:
        game = new_game()
        civilian = next(s.seat for s in game.seats if s.role is PlayerRole.CIVILIAN)

        rejection = game.clue_rejection(seat=civilian, clue=clue)

        assert rejection is not None
        assert reason in rejection.reason
        assert rejection.retryable

    def test_repeated_clue_is_rejected_after_normalisation(self) -> None:
        game = new_game()
        give_clue(game, seat=0, clue="Spots")

        rejection = game.clue_rejection(seat=1, clue="spot.")

        assert rejection is not None
        assert "already given" in rejection.reason

    def test_imposter_saying_the_word_is_not_told_why(self) -> None:
        game = new_game()

        rejection = game.clue_rejection(seat=game.imposters[0], clue=WORD)

        assert rejection is not None
        assert WORD not in rejection.reason
        assert not rejection.retryable

    def test_submitting_an_invalid_clue_raises(self) -> None:
        game = new_game()
        game.start_turn(0)

        with pytest.raises(InvalidActionError, match="Invalid clue"):
            game.submit_clue(seat=0, clue="two words", private_reasoning="")

    def test_clue_is_cleaned_and_reasoning_truncated(self) -> None:
        game = new_game(reasoning_word_cap=2)
        give_clue(game, seat=0, clue=" Spots! ", reasoning="one two three")

        event = game.events_of_type(ClueGivenEvent)[0]

        assert event.clue == "Spots"
        assert event.private_reasoning == "one two"
        assert event.reasoning_truncated

    def test_pass_is_recorded_as_no_clue(self) -> None:
        game = new_game()
        give_clue(game, seat=0, clue=None)

        assert game.view_for(1).clues[0].clue is None
        assert game.view_for(0).scratchpad[0].action == "passed"

    def test_round_ends_after_every_seat(self) -> None:
        game = new_game(player_count=3)

        for seat in range(3):
            give_clue(game, seat=seat, clue=f"clue{seat}")

        assert (game.phase, game.round) == (GamePhase.CLUE, 2)
        assert game.pending_seats == [0, 1, 2]


class TestStatements:
    def test_statement_is_truncated_and_redacted(self) -> None:
        game = new_game(clue_rounds=1, statement_word_cap=4)

        for seat in range(4):
            give_clue(game, seat=seat, clue=f"clue{seat}")

        game.start_turn(0)
        game.submit_statement(
            seat=0, statement="Giraffes are tall animals indeed.", private_reasoning=""
        )

        event = game.events_of_type(StatementMadeEvent)[0]

        assert event.statement == f"{REDACTION} are tall animals"
        assert event.truncated
        assert game.view_for(1).statements[0].statement == event.statement


class TestVotes:
    def test_vote_must_name_another_player(self) -> None:
        game = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(game)

        unknown = game.vote_rejection(voter=0, vote_for="Nobody")
        own = game.vote_rejection(voter=0, vote_for=game.seats[0].name)
        other = game.vote_rejection(voter=0, vote_for=f" {game.seats[1].name.upper()} ")

        assert unknown is not None
        assert "is not a player" in unknown.reason
        assert own is not None
        assert "yourself" in own.reason
        assert other is None

    def test_submitting_an_invalid_vote_raises(self) -> None:
        game = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(game)
        game.start_turn(0)

        with pytest.raises(InvalidActionError, match="Invalid vote"):
            game.submit_vote(voter=0, vote_for=game.seats[0].name, private_reasoning="")

    def test_vote_phase_is_parallel(self) -> None:
        game = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(game)

        game.start_turn(3)
        game.start_turn(1)

        assert game.phase is GamePhase.VOTE
        assert not game.is_sequential

    def test_last_vote_reveals_and_tallies(self) -> None:
        game = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(game)

        vote(game, {0: 1, 1: 0, 2: 1, 3: None})

        revealed = game.events_of_type(VotesRevealedEvent)[0]

        assert revealed.counts == [1, 2, 0, 0]
        assert revealed.caught == [1]
        assert game.phase is GamePhase.GUESS
        assert game.pending_seats == game.imposters

    def test_tie_catches_nobody_and_imposter_wins(self) -> None:
        game = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(game)

        vote(game, {0: 1, 1: 0, 2: 0, 3: 1})
        guess_all(game, {})

        outcome = game.events_of_type(OutcomeEvent)[0]

        assert outcome.caught == []
        assert outcome.outcome is GameOutcome.IMPOSTER_WINS
        assert game.phase is GamePhase.DEBRIEF


class TestOutcome:
    def play_to_outcome(self, *, guess: str, judge_verdict: bool | None = None) -> Game:
        """Catch the single imposter and let it guess."""
        game = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(game)
        imposter = game.imposters[0]
        vote(game, votes_against(game, [imposter, (imposter + 1) % 4]))
        game.start_turn(imposter)
        game.submit_guess(
            seat=imposter, guess=guess, private_reasoning="", judge_verdict=judge_verdict
        )

        return game

    def test_caught_imposter_with_wrong_guess_loses(self) -> None:
        game = self.play_to_outcome(guess="zebra")

        assert game.outcome is GameOutcome.CIVILIANS_WIN

    def test_caught_imposter_with_exact_guess_steals_the_win(self) -> None:
        game = self.play_to_outcome(guess=" Giraffes. ")

        assert game.outcome is GameOutcome.IMPOSTER_STEALS

    def test_judge_verdict_decides_inexact_guesses(self) -> None:
        game = self.play_to_outcome(guess="camelopard", judge_verdict=True)

        assert game.outcome is GameOutcome.IMPOSTER_STEALS
        assert game.events_of_type(GuessMadeEvent)[0].judged_by == "judge"

    def test_empty_guess_is_never_correct(self) -> None:
        game = self.play_to_outcome(guess="", judge_verdict=True)

        assert game.outcome is GameOutcome.CIVILIANS_WIN

    def test_debrief_finishes_the_game(self) -> None:
        game = self.play_to_outcome(guess="zebra")

        for seat in game.pending_seats:
            game.start_turn(seat)

        for seat in range(4):
            game.submit_reflection(seat=seat, reflection=" I learned a lot. ")

        assert game.phase is GamePhase.DONE
        assert game.is_over
        assert isinstance(game.events[-1], GameFinishedEvent)
        assert game.events[-1].outcome is GameOutcome.CIVILIANS_WIN


class TestMultipleImposters:
    def setup_vote(self) -> Game:
        """Create a game with 7 seats and 3 imposters, ready to vote."""
        game = new_game(
            player_count=7, imposter_count=3, clue_rounds=1, discussion_rounds=0
        )
        play_until_vote(game)

        return game

    def catch_all_imposters(self, game: Game) -> None:
        """Vote so that the imposters get 3, 2 and 2 votes and are all caught."""
        first, second, third = game.imposters
        civilians = [seat for seat in range(7) if seat not in game.imposters]
        targets: dict[int, int | None] = {first: second, second: third, third: first}
        targets.update(zip(civilians, [first, first, second, third], strict=True))
        vote(game, targets)

    def test_all_imposters_caught_and_wrong_lose(self) -> None:
        game = self.setup_vote()
        self.catch_all_imposters(game)

        assert game.events_of_type(VotesRevealedEvent)[0].caught == game.imposters

        guess_all(game, {})

        assert game.outcome is GameOutcome.CIVILIANS_WIN

    def test_one_correct_guess_steals_the_win_for_the_team(self) -> None:
        game = self.setup_vote()
        self.catch_all_imposters(game)
        guess_all(game, {game.imposters[2]: WORD})

        assert game.outcome is GameOutcome.IMPOSTER_STEALS

    def test_one_uncaught_imposter_wins_for_the_team(self) -> None:
        game = self.setup_vote()
        first, second, _ = game.imposters
        vote(game, {voter: first if voter != first else second for voter in range(7)})

        assert game.outcome is None

        guess_all(game, {})

        assert game.outcome is GameOutcome.IMPOSTER_WINS

    def test_every_imposter_guesses(self) -> None:
        game = self.setup_vote()
        vote(game, {voter: None for voter in range(7)})

        assert game.pending_seats == game.imposters

        guess_all(game, {})

        assert game.phase is GamePhase.DEBRIEF


class TestAbort:
    def test_abort_stops_the_game(self) -> None:
        game = new_game()
        game.abort("user request")

        assert game.phase is GamePhase.ABORTED
        assert game.pending_seats == []
        assert isinstance(game.events[-1], GameAbortedEvent)

        with pytest.raises(InvalidActionError, match="already over"):
            game.abort("again")

        with pytest.raises(InvalidActionError, match="no turn to start"):
            game.start_turn(0)

    def test_exceeding_the_token_budget_aborts(self) -> None:
        game = new_game(token_budget=100)
        game.record_usage(seat=0, model_id="m", input_tokens=60, output_tokens=30)

        assert not game.is_over

        game.record_usage(
            seat=1, model_id="m", input_tokens=5, output_tokens=5, thinking_tokens=1
        )

        assert game.tokens_used == 101
        assert game.phase is GamePhase.ABORTED
        assert "token budget" in game.events[-1].model_dump()["reason"]

    def test_usage_after_the_game_is_over_is_still_recorded(self) -> None:
        game = new_game(token_budget=1)
        game.record_usage(seat=0, model_id="m", input_tokens=5, output_tokens=0)
        game.record_usage(seat=1, model_id="m", input_tokens=5, output_tokens=0)

        assert game.tokens_used == 10
        assert game.events[-1].model_dump()["type"] == "usage"


class TestViews:
    def test_civilian_sees_the_word_and_imposter_the_hint(self) -> None:
        game = new_game(imposter_hint=True, hint="savanna")
        imposter = game.imposters[0]
        imposter_view = game.view_for(imposter)
        civilian_view = game.view_for((imposter + 1) % 4)

        assert (imposter_view.word, imposter_view.hint) == (None, "savanna")
        assert (civilian_view.word, civilian_view.hint) == (WORD, None)
        assert imposter_view.role is PlayerRole.IMPOSTER

    def test_category_is_hidden_when_not_public(self) -> None:
        assert new_game(public_category=False).view_for(0).category is None

    def test_view_shows_rules_and_players(self) -> None:
        view = new_game(identity_mode=IdentityMode.SEAT).view_for(2)

        assert view.name == "Player 3"
        assert view.players[0].name == "Player 1"
        assert [player.seat for player in other_players(view)] == [0, 1, 3]
        assert view.rules.player_count == 4

    def test_scratchpad_holds_only_own_turns(self) -> None:
        game = new_game()
        give_clue(game, seat=0, clue="tall", reasoning="mine")
        give_clue(game, seat=1, clue="spots", reasoning="theirs")

        scratchpad = game.view_for(0).scratchpad

        assert [entry.private_reasoning for entry in scratchpad] == ["mine"]

    def test_own_vote_stays_out_of_the_scratchpad_until_revealed(self) -> None:
        game = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(game)
        game.start_turn(0)
        game.start_turn(1)
        game.submit_vote(voter=0, vote_for=game.seats[1].name, private_reasoning="hm")
        view = game.view_for(0)

        assert all(entry.phase is not GamePhase.VOTE for entry in view.scratchpad)
        assert view.vote_result is None

    def test_debrief_reveals_word_roles_votes_and_guesses(self) -> None:
        game = new_game(clue_rounds=1, discussion_rounds=0, public_category=False)
        play_until_vote(game)
        vote(game, {0: None, 1: 0, 2: 0, 3: 0})
        guess_all(game, {})
        view = game.view_for(1)

        assert view.word == WORD
        assert view.category == "animals"
        assert view.reveal is not None
        assert view.reveal.imposters == game.imposters
        assert view.reveal.guesses[0].guess == "wrong"
        assert view.vote_result is not None
        assert [e.action for e in view.scratchpad if e.phase is GamePhase.VOTE] == [
            f"voted for {game.seats[0].name}"
        ]
        assert "abstained" in [entry.action for entry in game.view_for(0).scratchpad]
