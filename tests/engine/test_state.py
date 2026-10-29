from typing import Any

import pytest

from imposter.engine.config import (
    GameConfig,
    GameOutcome,
    GamePhase,
    IdentityMode,
    PlayerConfig,
    PlayerRole,
    SecretWord,
)
from imposter.engine.errors import GameSetupError, InvalidActionError
from imposter.engine.events import (
    ClueGivenEvent,
    GameAbortedEvent,
    GameFinishedEvent,
    GameStartedEvent,
    OutcomeEvent,
    RoleAssignedEvent,
    StatementMadeEvent,
    VotesRevealedEvent,
)
from imposter.engine.rules import REDACTION
from imposter.engine.state import GameState

WORD = "giraffe"


def new_game(
    *, player_count: int = 4, hint: str | None = None, **options: Any
) -> GameState:
    """Create a seeded game with `player_count` seats in the first clue round."""
    config = GameConfig.model_validate(
        {
            "category": "animals",
            "players": [{"model_id": f"model-{seat}"} for seat in range(player_count)],
            "seed": 7,
            **options,
        }
    )

    return GameState.create(
        config=config, secret=SecretWord(word=WORD, category="animals", hint=hint)
    )


def give_clue(
    state: GameState, *, seat: int, clue: str | None, reasoning: str = ""
) -> None:
    """Start the seat's turn and submit a clue."""
    state.start_turn(seat)
    state.submit_clue(seat=seat, clue=clue, private_reasoning=reasoning)


def play_until_vote(state: GameState) -> None:
    """Play every clue and discussion turn with distinct, valid actions."""
    while state.phase in (GamePhase.CLUE, GamePhase.DISCUSSION):
        seat = state.pending_seats[0]

        if state.phase is GamePhase.CLUE:
            give_clue(state, seat=seat, clue=f"clue{state.round}x{seat}")
        else:
            state.start_turn(seat)
            state.submit_statement(seat=seat, statement="Hello.", private_reasoning="")


def vote(state: GameState, targets: dict[int, int | None]) -> None:
    """Cast every vote, by seat, with `None` as an abstention."""
    for voter in state.pending_seats:
        state.start_turn(voter)

    for voter, target in targets.items():
        name = None if target is None else state.seats[target].name
        state.submit_vote(voter=voter, vote_for=name, private_reasoning="")


def guess_all(state: GameState, guesses: dict[int, str]) -> None:
    """Let every imposter guess in turn."""
    for seat in state.imposters:
        state.start_turn(seat)
        state.submit_guess(
            seat=seat, guess=guesses.get(seat, "wrong"), private_reasoning=""
        )


def votes_against(state: GameState, targets: list[int]) -> dict[int, int | None]:
    """Have every seat vote for the first target that is not itself."""
    return {
        voter: next(target for target in targets if target != voter)
        for voter in range(len(state.seats))
    }


class TestCreate:
    def test_setup_emits_start_roles_and_first_round(self) -> None:
        state = new_game()

        assert isinstance(state.events[0], GameStartedEvent)
        assert [type(event) for event in state.events[1:5]] == [RoleAssignedEvent] * 4
        assert state.phase is GamePhase.CLUE
        assert state.round == 1
        assert state.pending_seats == [0, 1, 2, 3]
        assert [event.seq for event in state.events] == list(range(len(state.events)))

    def test_seed_fixes_seats_roles_and_names(self) -> None:
        first, second = new_game(player_count=8), new_game(player_count=8)

        assert first.seats == second.seats
        assert first.game_id != second.game_id

    def test_roles_have_the_configured_number_of_imposters(self) -> None:
        state = new_game(player_count=8, imposter_count=3)

        assert len(state.imposters) == 3
        assert sum(seat.role is PlayerRole.CIVILIAN for seat in state.seats) == 5

    def test_enabled_hint_must_exist(self) -> None:
        with pytest.raises(GameSetupError, match="no hint"):
            new_game(imposter_hint=True)

    def test_hint_must_differ_from_word(self) -> None:
        with pytest.raises(GameSetupError, match="differ"):
            new_game(imposter_hint=True, hint="Giraffes")

    def test_started_game_cannot_start_again(self) -> None:
        with pytest.raises(InvalidActionError, match="already started"):
            new_game().start()


class TestTurns:
    def test_sequential_phase_only_starts_the_next_seat(self) -> None:
        state = new_game()

        with pytest.raises(InvalidActionError, match="turn of seat 0"):
            state.start_turn(1)

    def test_turn_cannot_start_twice(self) -> None:
        state = new_game()
        state.start_turn(0)

        with pytest.raises(InvalidActionError, match="no turn to start"):
            state.start_turn(0)

    def test_action_needs_a_started_turn(self) -> None:
        state = new_game()

        with pytest.raises(InvalidActionError, match="no started turn"):
            state.submit_clue(seat=0, clue="tall", private_reasoning="")

    def test_action_must_match_the_phase(self) -> None:
        state = new_game()
        state.start_turn(0)

        with pytest.raises(InvalidActionError, match="cannot act in phase discussion"):
            state.submit_statement(seat=0, statement="Hi.", private_reasoning="")


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
        state = new_game()
        civilian = next(
            seat.seat for seat in state.seats if seat.role is PlayerRole.CIVILIAN
        )

        rejection = state.clue_rejection(seat=civilian, clue=clue)

        assert rejection is not None
        assert reason in rejection.reason
        assert rejection.retryable

    def test_repeated_clue_is_rejected_after_normalisation(self) -> None:
        state = new_game()
        give_clue(state, seat=0, clue="Spots")

        rejection = state.clue_rejection(seat=1, clue="spot.")

        assert rejection is not None
        assert "already given" in rejection.reason

    def test_imposter_saying_the_word_is_not_told_why(self) -> None:
        state = new_game()
        imposter = state.imposters[0]

        rejection = state.clue_rejection(seat=imposter, clue=WORD)

        assert rejection is not None
        assert WORD not in rejection.reason
        assert not rejection.retryable

    def test_submitting_an_invalid_clue_raises(self) -> None:
        state = new_game()
        state.start_turn(0)

        with pytest.raises(InvalidActionError, match="invalid clue"):
            state.submit_clue(seat=0, clue="two words", private_reasoning="")

    def test_clue_is_cleaned_and_reasoning_truncated(self) -> None:
        state = new_game(reasoning_word_cap=2)
        give_clue(state, seat=0, clue=" Spots! ", reasoning="one two three")

        event = state.events[-1]

        assert isinstance(event, ClueGivenEvent)
        assert event.clue == "Spots"
        assert event.private_reasoning == "one two"
        assert event.reasoning_truncated

    def test_pass_is_recorded_as_no_clue(self) -> None:
        state = new_game()
        give_clue(state, seat=0, clue=None)

        assert state.view_for(1).clues[0].clue is None
        assert state.view_for(0).scratchpad[0].action == "passed"

    def test_round_ends_after_every_seat(self) -> None:
        state = new_game(player_count=3)

        for seat in range(3):
            give_clue(state, seat=seat, clue=f"clue{seat}")

        assert (state.phase, state.round) == (GamePhase.CLUE, 2)
        assert state.pending_seats == [0, 1, 2]


class TestStatements:
    def test_statement_is_truncated_and_redacted(self) -> None:
        state = new_game(clue_rounds=1, statement_word_cap=4)

        for seat in range(4):
            give_clue(state, seat=seat, clue=f"clue{seat}")

        state.start_turn(0)
        state.submit_statement(
            seat=0, statement="Giraffes are tall animals indeed.", private_reasoning=""
        )

        event = state.events[-1]

        assert isinstance(event, StatementMadeEvent)
        assert event.statement == f"{REDACTION} are tall animals"
        assert event.truncated
        assert state.view_for(1).statements[0].statement == event.statement


class TestVotes:
    def test_vote_must_name_another_player(self) -> None:
        state = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(state)

        unknown = state.vote_rejection(voter=0, vote_for="Nobody")
        own = state.vote_rejection(voter=0, vote_for=state.seats[0].name)
        other = state.vote_rejection(voter=0, vote_for=f" {state.seats[1].name.upper()} ")

        assert unknown is not None
        assert "is not a player" in unknown.reason
        assert own is not None
        assert "yourself" in own.reason
        assert other is None

    def test_submitting_an_invalid_vote_raises(self) -> None:
        state = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(state)
        state.start_turn(0)

        with pytest.raises(InvalidActionError, match="invalid vote"):
            state.submit_vote(voter=0, vote_for=state.seats[0].name, private_reasoning="")

    def test_vote_phase_is_parallel(self) -> None:
        state = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(state)

        state.start_turn(3)
        state.start_turn(1)

        assert state.phase is GamePhase.VOTE
        assert not state.is_sequential

    def test_last_vote_reveals_and_tallies(self) -> None:
        state = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(state)

        vote(state, {0: 1, 1: 0, 2: 1, 3: None})

        revealed = next(e for e in state.events if isinstance(e, VotesRevealedEvent))

        assert revealed.counts == [1, 2, 0, 0]
        assert revealed.caught == [1]
        assert state.phase is GamePhase.GUESS
        assert state.pending_seats == state.imposters

    def test_tie_catches_nobody_and_imposter_wins(self) -> None:
        state = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(state)

        vote(state, {0: 1, 1: 0, 2: 0, 3: 1})
        guess_all(state, {})

        outcome = next(e for e in state.events if isinstance(e, OutcomeEvent))

        assert outcome.caught == []
        assert outcome.outcome is GameOutcome.IMPOSTER_WINS
        assert state.phase is GamePhase.DEBRIEF


class TestOutcome:
    def play_to_outcome(
        self, *, guess: str, judge_verdict: bool | None = None
    ) -> GameState:
        """Catch the single imposter and let it guess."""
        state = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(state)
        imposter = state.imposters[0]
        vote(state, votes_against(state, [imposter, (imposter + 1) % 4]))
        state.start_turn(imposter)
        state.submit_guess(
            seat=imposter, guess=guess, private_reasoning="", judge_verdict=judge_verdict
        )

        return state

    def test_caught_imposter_with_wrong_guess_loses(self) -> None:
        state = self.play_to_outcome(guess="zebra")

        assert state.outcome is GameOutcome.CIVILIANS_WIN

    def test_caught_imposter_with_exact_guess_steals_the_win(self) -> None:
        state = self.play_to_outcome(guess=" Giraffes. ")

        assert state.outcome is GameOutcome.IMPOSTER_STEALS

    def test_judge_verdict_decides_inexact_guesses(self) -> None:
        state = self.play_to_outcome(guess="camelopard", judge_verdict=True)
        judged = [e for e in state.events if e.model_dump().get("method") == "judge"]

        assert state.outcome is GameOutcome.IMPOSTER_STEALS
        assert len(judged) == 1

    def test_empty_guess_is_never_correct(self) -> None:
        state = self.play_to_outcome(guess="", judge_verdict=True)

        assert state.outcome is GameOutcome.CIVILIANS_WIN

    def test_debrief_finishes_the_game(self) -> None:
        state = self.play_to_outcome(guess="zebra")

        for seat in state.pending_seats:
            state.start_turn(seat)

        for seat in range(4):
            state.submit_reflection(seat=seat, reflection=" I learned a lot. ")

        assert state.phase is GamePhase.DONE
        assert state.is_over
        assert isinstance(state.events[-1], GameFinishedEvent)
        assert state.events[-1].outcome is GameOutcome.CIVILIANS_WIN


class TestMultipleImposters:
    def setup_vote(self) -> GameState:
        """Create a game with 7 seats and 3 imposters, ready to vote."""
        state = new_game(
            player_count=7, imposter_count=3, clue_rounds=1, discussion_rounds=0
        )
        play_until_vote(state)

        return state

    def catch_all_imposters(self, state: GameState) -> None:
        """Vote so that the imposters get 3, 2 and 2 votes and are all caught."""
        first, second, third = state.imposters
        civilians = [seat for seat in range(7) if seat not in state.imposters]
        targets: dict[int, int | None] = {first: second, second: third, third: first}
        targets.update(zip(civilians, [first, first, second, third], strict=True))
        vote(state, targets)

    def test_all_imposters_caught_and_wrong_lose(self) -> None:
        state = self.setup_vote()
        self.catch_all_imposters(state)

        assert state.events[-2].model_dump()["caught"] == sorted(state.imposters)

        guess_all(state, {})

        assert state.outcome is GameOutcome.CIVILIANS_WIN

    def test_one_correct_guess_steals_the_win_for_the_team(self) -> None:
        state = self.setup_vote()
        self.catch_all_imposters(state)
        guess_all(state, {state.imposters[2]: WORD})

        assert state.outcome is GameOutcome.IMPOSTER_STEALS

    def test_one_uncaught_imposter_wins_for_the_team(self) -> None:
        state = self.setup_vote()
        first, second, _ = state.imposters
        vote(state, {voter: first if voter != first else second for voter in range(7)})

        assert state.outcome is None

        guess_all(state, {})

        assert state.outcome is GameOutcome.IMPOSTER_WINS

    def test_every_imposter_guesses(self) -> None:
        state = self.setup_vote()
        vote(state, {voter: None for voter in range(7)})

        assert state.pending_seats == state.imposters

        guess_all(state, {})

        assert state.phase is GamePhase.DEBRIEF


class TestAbort:
    def test_abort_stops_the_game(self) -> None:
        state = new_game()
        state.abort("user request")

        assert state.phase is GamePhase.ABORTED
        assert state.pending_seats == []
        assert isinstance(state.events[-1], GameAbortedEvent)

        with pytest.raises(InvalidActionError, match="already over"):
            state.abort("again")

        with pytest.raises(InvalidActionError, match="no turn to start"):
            state.start_turn(0)

    def test_exceeding_the_token_budget_aborts(self) -> None:
        state = new_game(token_budget=100)
        state.record_usage(seat=0, model_id="m", input_tokens=60, output_tokens=30)

        assert not state.is_over

        state.record_usage(
            seat=1, model_id="m", input_tokens=5, output_tokens=5, thinking_tokens=1
        )

        assert state.tokens_used == 101
        assert state.phase is GamePhase.ABORTED
        assert "token budget" in state.events[-1].model_dump()["reason"]

    def test_usage_after_the_game_is_over_is_still_recorded(self) -> None:
        state = new_game(token_budget=1)
        state.record_usage(seat=0, model_id="m", input_tokens=5, output_tokens=0)
        state.record_usage(seat=1, model_id="m", input_tokens=5, output_tokens=0)

        assert state.tokens_used == 10
        assert state.events[-1].model_dump()["type"] == "usage"


class TestViews:
    def test_civilian_sees_the_word_and_imposter_the_hint(self) -> None:
        state = new_game(imposter_hint=True, hint="savanna")
        imposter = state.imposters[0]
        civilian = (imposter + 1) % 4

        imposter_view = state.view_for(imposter)
        civilian_view = state.view_for(civilian)

        assert (imposter_view.word, imposter_view.hint) == (None, "savanna")
        assert (civilian_view.word, civilian_view.hint) == (WORD, None)
        assert imposter_view.role is PlayerRole.IMPOSTER

    def test_category_is_hidden_when_not_public(self) -> None:
        state = new_game(public_category=False)

        assert state.view_for(0).category is None

    def test_view_shows_rules_and_players(self) -> None:
        state = new_game(identity_mode=IdentityMode.SEAT)
        view = state.view_for(2)

        assert view.name == "Player 3"
        assert view.name_of(0) == "Player 1"
        assert [player.seat for player in view.other_players] == [0, 1, 3]
        assert view.rules.player_count == 4

    def test_scratchpad_holds_only_own_turns(self) -> None:
        state = new_game()
        give_clue(state, seat=0, clue="tall", reasoning="mine")
        give_clue(state, seat=1, clue="spots", reasoning="theirs")

        assert [entry.private_reasoning for entry in state.view_for(0).scratchpad] == [
            "mine"
        ]

    def test_own_vote_stays_out_of_the_scratchpad_until_revealed(self) -> None:
        state = new_game(clue_rounds=1, discussion_rounds=0)
        play_until_vote(state)
        state.start_turn(0)
        state.start_turn(1)
        state.submit_vote(voter=0, vote_for=state.seats[1].name, private_reasoning="hm")

        assert all(
            entry.phase is not GamePhase.VOTE for entry in state.view_for(0).scratchpad
        )
        assert state.view_for(0).vote_result is None

    def test_debrief_reveals_word_roles_and_guesses(self) -> None:
        state = new_game(clue_rounds=1, discussion_rounds=0, public_category=False)
        play_until_vote(state)
        vote(state, {voter: None for voter in range(4)})
        guess_all(state, {})
        view = state.view_for(state.imposters[0])

        assert view.word == WORD
        assert view.category == "animals"
        assert view.reveal is not None
        assert view.reveal.imposters == state.imposters
        assert view.reveal.guesses[0].guess == "wrong"
        assert view.vote_result is not None


def test_models_identity_uses_display_names() -> None:
    config = GameConfig(
        category="animals",
        players=[PlayerConfig(model_id="m", model_display_name="Gemini Flash")] * 3,
        identity_mode=IdentityMode.MODELS,
    )
    state = GameState.create(config=config, secret=SecretWord(word=WORD))

    assert sorted(seat.name for seat in state.seats) == [
        "Gemini Flash #1",
        "Gemini Flash #2",
        "Gemini Flash #3",
    ]
