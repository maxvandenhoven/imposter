import json
from pathlib import Path

import pytest
from build_evalsets import (
    INSTRUCTION_END,
    INSTRUCTION_START,
    PLAYER_VIEW_RUBRIC_TYPE,
    QUALITY_RUBRIC_TYPE,
    SECRET_WORD_RUBRIC_TYPE,
    ClueLabel,
    LoggedCall,
    PlayerTurn,
    answer_field,
    clue_pairs,
    is_holdout,
    judge_case,
    load_labels,
    parse_view,
    player_case,
    player_suites,
    player_turns,
    save_labels,
)

from imposter.config import GameConfig, GamePhase, PlayerRole, SecretWord
from imposter.engine.game import Game
from imposter.engine.views import PlayerView
from imposter.judge.llm_judge import VALID_CLUE_TASK
from imposter.players.prompt import PlayerPromptRenderer

TRACE_ID = "4df186e0d4b246b5302ad4a2879196c1"


@pytest.fixture(scope="module")
def played_views() -> dict[str, PlayerView]:
    """Views of a full game: a clue turn, a discussion turn and both roles' debriefs.

    The discussion has a statement cut at the cap and an empty one, the imposter is
    caught and guesses wrong, so every section of the transcript is rendered.
    """
    config = GameConfig.model_validate(
        {"players": [{"model_id": f"model-{seat}"} for seat in range(4)], "seed": 7}
    )
    game = Game.create(config=config, secret=SecretWord(word="giraffe", category="x"))
    clues = iter(["neck", "savanna", None, "spots", "tall", "acacia", "zoo", "herd"])
    names = {seat.seat: seat.name for seat in game.seats}
    imposter = game.imposters[0]
    civilian = (imposter + 1) % len(names)
    views = {}

    while game.phase is GamePhase.CLUE:
        seat = game.pending_seats[0]

        if game.round == 2:
            views.setdefault("clue", game.view_for(seat))

        game.start_turn(seat)
        game.submit_clue(seat=seat, clue=next(clues), private_reasoning="Careful.")

    while game.phase is GamePhase.DISCUSSION:
        seat = game.pending_seats[0]

        if game.round == 2:
            views.setdefault("discussion", game.view_for(seat))

        statements = {1: "long " * 120, 2: ""}
        game.start_turn(seat)
        game.submit_statement(
            seat=seat,
            statement=statements.get(seat, f'Seat {seat} liked "neck".'),
            private_reasoning="Hm.",
        )

    for seat in list(game.pending_seats):
        target = names[imposter] if seat != imposter else names[civilian]
        game.start_turn(seat)
        game.submit_vote(voter=seat, vote_for=target, private_reasoning="Vote.")

    game.start_turn(imposter)
    game.submit_guess(
        seat=imposter, guess="horse", private_reasoning="Guess.", judge_verdict=False
    )
    views["debrief_civilian"] = game.view_for(civilian)
    views["debrief_imposter"] = game.view_for(imposter)

    return views


def logged_call(*, view: PlayerView, task: str, output: str = "") -> LoggedCall:
    """Wrap a rendered turn the way ADK logs it, preamble with markers included."""
    instruction = PlayerPromptRenderer().instruction(view)
    first = (
        f"The text between {INSTRUCTION_START} and {INSTRUCTION_END} below is your own "
        f"system instruction.\n{INSTRUCTION_START}\n{instruction}\n{INSTRUCTION_END}"
    )

    return LoggedCall(
        trace_id=TRACE_ID,
        agent=f"player_{view.seat}_{view.phase}",
        inputs=[first, task],
        output=output,
    )


@pytest.mark.parametrize("include_schema", [False, True])
def test_a_logged_clue_turn_parses_back_to_its_view(
    civilian_clue_view: PlayerView, include_schema: bool
) -> None:
    renderer = PlayerPromptRenderer()
    task = renderer.task(view=civilian_clue_view, include_schema=include_schema)
    call = logged_call(view=civilian_clue_view, task=task)

    view = parse_view(call=call, renderer=renderer)

    assert view == civilian_clue_view.model_copy(update={"game_id": TRACE_ID})


@pytest.mark.parametrize(
    "name", ["clue", "discussion", "debrief_civilian", "debrief_imposter"]
)
def test_every_evaluated_phase_parses_back_to_its_view(
    played_views: dict[str, PlayerView], name: str
) -> None:
    renderer = PlayerPromptRenderer()
    original = played_views[name]
    call = logged_call(view=original, task=renderer.task(view=original))

    view = parse_view(call=call, renderer=renderer)

    assert view == original.model_copy(update={"game_id": TRACE_ID})


def test_the_debrief_views_hold_the_whole_game(
    played_views: dict[str, PlayerView],
) -> None:
    view = played_views["debrief_imposter"]

    assert view.reveal is not None and view.reveal.guesses
    assert view.vote_result is not None
    assert any(statement.truncated for statement in view.statements)
    assert any(not statement.statement for statement in view.statements)


def test_a_retried_turn_is_not_parsed(civilian_clue_view: PlayerView) -> None:
    renderer = PlayerPromptRenderer()
    task = renderer.task(view=civilian_clue_view, retry_reason="the clue was repeated")
    call = logged_call(view=civilian_clue_view, task=task)

    assert parse_view(call=call, renderer=renderer) is None


def test_a_prompt_that_does_not_render_back_exactly_is_not_parsed(
    civilian_clue_view: PlayerView,
) -> None:
    renderer = PlayerPromptRenderer()
    call = logged_call(
        view=civilian_clue_view, task=renderer.task(view=civilian_clue_view) + " Extra."
    )

    assert parse_view(call=call, renderer=renderer) is None


def test_player_turns_know_the_word_and_whether_the_answer_said_it(
    played_views: dict[str, PlayerView],
) -> None:
    renderer = PlayerPromptRenderer()
    civilian = played_views["debrief_civilian"]
    clue_view = played_views["clue"]
    discussion_view = played_views["discussion"]
    calls = [
        logged_call(view=civilian, task=renderer.task(view=civilian)),
        logged_call(
            view=clue_view,
            task=renderer.task(view=clue_view),
            output='{"clue": "Giraffes"}',
        ),
        logged_call(
            view=discussion_view,
            task=renderer.task(view=discussion_view),
            output='{"statement": "It is surely a giraffe."}',
        ),
    ]

    turns = player_turns(calls=calls, renderer=renderer)

    assert [(turn.view.phase, turn.word, turn.said_word) for turn in turns] == [
        (GamePhase.DEBRIEF, "giraffe", False),
        (GamePhase.CLUE, "giraffe", True),
        (GamePhase.DISCUSSION, "giraffe", True),
    ]


def test_the_suites_split_clue_turns_by_role_and_collect_the_word_said_turns(
    played_views: dict[str, PlayerView],
) -> None:
    clue_view = played_views["clue"]
    civilian_view = clue_view.model_copy(update={"role": PlayerRole.CIVILIAN})
    imposter_view = clue_view.model_copy(update={"role": PlayerRole.IMPOSTER})
    turns = [
        PlayerTurn(view=civilian_view, word="giraffe", said_word=True),
        PlayerTurn(view=imposter_view, word="giraffe", said_word=False),
    ]

    suites = player_suites(turns)

    assert [turn.view.role for turn in suites[(GamePhase.CLUE, "civilian")]] == [
        PlayerRole.CIVILIAN
    ]
    assert [turn.view.role for turn in suites[(GamePhase.CLUE, "imposter")]] == [
        PlayerRole.IMPOSTER
    ]
    assert suites[(GamePhase.CLUE, "word_said")] == turns[:1]


def test_answer_field_reads_the_json_after_reasoning_text() -> None:
    output = 'We need JSON with "clue". {"clue": "say \\"hi\\"", "private_reasoning": ""}'

    assert answer_field(output=output, field="clue") == 'say "hi"'
    assert answer_field(output="no answer", field="clue") is None


def test_clue_pairs_come_from_player_answers_and_judge_tasks(
    civilian_clue_view: PlayerView,
) -> None:
    task = PlayerPromptRenderer().task(view=civilian_clue_view)
    player_call = logged_call(
        view=civilian_clue_view, task=task, output='{"clue": "Tall"}'
    )
    judge_call = LoggedCall(
        trace_id="other",
        agent="judge",
        inputs=[VALID_CLUE_TASK.format(word="Lighthouse", clue="Keeper")],
        output='{"verdict": true}',
    )

    pairs = clue_pairs([player_call, judge_call])

    assert pairs == {("giraffe", "tall"), ("lighthouse", "keeper")}


def test_labels_survive_a_save_and_load(tmp_path: Path) -> None:
    labels = [
        ClueLabel(word="wallet", clue="purse", legal=True, synonym=True, note="Close."),
        ClueLabel(word="echo", clue="canyon"),
    ]
    path = tmp_path / "labels.yaml"

    save_labels(labels=labels, path=path)

    assert load_labels(path) == sorted(labels, key=lambda label: label.word)
    assert path.read_text().startswith("# Hand-made labels")


def test_a_judge_case_expects_the_labelled_verdict() -> None:
    case = judge_case(
        ClueLabel(word="gratitude", clue="thanks", legal=True, synonym=True)
    )
    invocation = case.conversation[0] if case.conversation else None

    assert case.eval_id == "synonym-gratitude-thanks"
    assert invocation is not None and invocation.final_response is not None
    assert invocation.final_response.parts is not None
    assert json.loads(invocation.final_response.parts[0].text or "") == {"verdict": True}
    assert "Clue: thanks" in ((invocation.user_content.parts or [])[0].text or "")


def test_a_player_case_carries_its_view_to_the_agent_and_the_metrics(
    civilian_clue_view: PlayerView,
) -> None:
    renderer = PlayerPromptRenderer()
    turn = PlayerTurn(view=civilian_clue_view, word="giraffe", said_word=False)

    case = player_case(turn=turn, suite="civilian", renderer=renderer, repeat=2)
    rubrics = {
        rubric.type: rubric.rubric_content.text_property for rubric in case.rubrics or []
    }
    prompt = (case.conversation or [])[0].user_content.parts or []

    assert case.eval_id.endswith("-repeat_2")
    assert case.session_input is not None
    assert (
        PlayerView.model_validate(case.session_input.state["view"]) == civilian_clue_view
    )
    assert rubrics[PLAYER_VIEW_RUBRIC_TYPE] == civilian_clue_view.model_dump_json()
    assert rubrics[SECRET_WORD_RUBRIC_TYPE] == "giraffe"
    assert '"giraffe"' in (rubrics[QUALITY_RUBRIC_TYPE] or "")
    assert renderer.instruction(civilian_clue_view) in (prompt[0].text or "")


def test_the_holdout_split_is_stable_and_by_word() -> None:
    words = [f"word{index}" for index in range(200)]
    holdout = [word for word in words if is_holdout(word)]

    assert holdout == [word for word in words if is_holdout(word.upper())]
    assert 0.2 < len(holdout) / len(words) < 0.4
