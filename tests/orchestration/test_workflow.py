import asyncio
import json
from collections.abc import AsyncGenerator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from conftest import ReplayLlm, fake_builder, play_workflow, run_events
from fakes import RandomPlayer, ScriptedPlayer, ScriptStep
from google.adk.agents.context import Context
from google.adk.events import Event
from google.adk.labs.classifiers import (
    BaseClassifier,
    BinaryAnswer,
    ClassifierInput,
    ClassifierResponse,
    Question,
)
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import Field

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
    GAME_EVENT_ADAPTER,
    BaseGameEvent,
    ClueGivenEvent,
    GameAbortedEvent,
    GuessMadeEvent,
    PlayerErrorEvent,
    ReflectionEvent,
    TurnStartedEvent,
    VoteCastEvent,
)
from imposter.engine.game import GAME_STATE_KEY, Game, GameSnapshot
from imposter.engine.responses import (
    ClueResponse,
    DebriefResponse,
    DiscussionResponse,
    GuessResponse,
    PhaseResponse,
    VoteResponse,
)
from imposter.engine.views import PlayerView
from imposter.judge.judge import Judge
from imposter.models.catalog import ModelCatalog, ModelCatalogEntry
from imposter.orchestration.setup import GameRequest
from imposter.orchestration.workflow import (
    GAME_EVENT_METADATA_KEY,
    OVER_ROUTE,
    REQUEST_STATE_KEY,
    TURN_ROUTE,
    WORKFLOW_NAME,
)
from imposter.players.base import PlayerProtocol, TurnUsage, UsageRecorder
from imposter.players.llm_player import LlmPlayerSeating
from imposter.words.generator import WordGenerator
from imposter.words.options import SecretWordResolver, WordMode, WordOptions
from imposter.words.picker import WordPicker

SNAPSHOTS_DIR = Path(__file__).with_name("snapshots")

GOLDEN_GAMES = {
    "plain": (4, 0.0, 3),
    "blunders": (5, 0.12, 33),
    "eight_seats": (8, 0.0, 2),
}
"""The seat count, blunder rate and seed of each golden game."""


@pytest.mark.parametrize("name", list(GOLDEN_GAMES))
async def test_workflow_plays_the_golden_games_event_for_event(name: str) -> None:
    count, blunder_rate, seed = GOLDEN_GAMES[name]
    players = [{"model_id": f"model-{seat % 3}"} for seat in range(count)]
    config = GameConfig.model_validate({"players": players, "seed": seed})
    game = Game.create(
        config=config,
        secret=SecretWord(word="giraffe", category="animals"),
        game_id=f"golden-{name}",
    )

    def players_for(game: Game) -> list[RandomPlayer]:
        return [
            RandomPlayer(
                seed=seed * 100 + seat.seat,
                blunder_rate=blunder_rate,
                usage=TurnUsage(
                    model_id=seat.player.model_id, input_tokens=90, output_tokens=10
                ),
            )
            for seat in game.seats
        ]

    played = await play_workflow(fake_builder(players_for=players_for), game=game)

    golden = json.loads((SNAPSHOTS_DIR / f"random_game_{name}.json").read_text())
    events = [e.model_dump(mode="json", exclude={"timestamp"}) for e in played.events]
    assert events == golden


WORD = "giraffe"


class RecordingClassifier(BaseClassifier):
    """A classifier that says yes to every guess and to clues starting with `bad`.

    Attributes:
        model: The name of the fake model.
        judged: The candidates the classifier was asked about, with the word.
    """

    model: str | BaseLlm = "fake"
    judged: list[tuple[str, str]] = Field(default_factory=list)

    async def classify(
        self, *, input: ClassifierInput, questions: Mapping[str, Question]
    ) -> ClassifierResponse:
        """Record a question and answer it."""
        assert isinstance(input, dict)
        candidate = str(input.get("guess") or input["clue"])
        self.judged.append((candidate, str(input["secret_word"])))
        is_yes = "guess" in input or candidate.startswith("bad")
        answer = BinaryAnswer(probability=1.0 if is_yes else 0.0)

        return ClassifierResponse(answers=dict.fromkeys(questions, answer))


class RecordingJudge(Judge):
    """A judge on a recording classifier: accepts guesses, rejects clues with `bad`."""

    def __init__(self) -> None:
        super().__init__(RecordingClassifier())

    @property
    def judged(self) -> list[tuple[str, str]]:
        """The candidates that reached the classifier, with the word."""
        assert isinstance(self.classifier, RecordingClassifier)

        return self.classifier.judged


async def play(
    game: Game, *, players: Sequence[PlayerProtocol], judge: Judge | None = None
) -> Game:
    """Play a game that is already set up through the workflow, with the given players."""
    builder = fake_builder(players_for=lambda _: players, judge=judge)

    return await play_workflow(builder, game=game)


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

    game = await play(game, players=players)

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

    game = await play(game, players=scripted_players(game, guess="Giraffes"))

    assert game.outcome is GameOutcome.IMPOSTER_STEALS


async def test_guess_judge_decides_inexact_guesses_only() -> None:
    judge = RecordingJudge()
    game = new_game()
    game = await play(
        game, players=scripted_players(game, guess="camelopard"), judge=judge
    )

    assert judge.judged[-1:] == [("camelopard", WORD)]
    assert game.events_of_type(GuessMadeEvent)[0].judged_by == "judge"
    assert game.outcome is GameOutcome.IMPOSTER_STEALS


async def test_invalid_clue_is_retried_with_the_reason() -> None:
    game = new_game()
    players = scripted_players(game)
    civilian = next(s.seat for s in game.seats if s.role is PlayerRole.CIVILIAN)
    players[civilian].script.insert(0, ClueResponse(clue="long neck"))

    game = await play(game, players=players)

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

    game = await play(game, players=players)

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

    game = await play(game, players=players, judge=judge)

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

    game = await play(game, players=players, judge=judge)

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

    game = await play(game, players=players, judge=judge)

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

    game = await play(game, players=players)

    revealed = next(e for e in game.events if e.model_dump()["type"] == "votes_revealed")

    assert revealed.model_dump()["votes"][seat]["target"] is None
    assert len(errors(game)) == 1


async def test_failing_player_gets_the_phase_fallback() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=1)
    players = scripted_players(game)
    players[0].script[1] = RuntimeError("model unavailable")

    game = await play(game, players=players)

    assert errors(game) == ["player failed: model unavailable"]
    assert game.view_for(0).statements[0].statement == ""
    assert game.phase is GamePhase.DONE


async def test_failing_guess_and_debrief_fall_back_to_empty_answers() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    imposter = game.imposters[0]
    players[imposter].script[-2:] = [RuntimeError("down"), RuntimeError("still down")]

    game = await play(game, players=players)

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

    game = await play(game, players=players)

    assert players[0].retry_reasons[1] == "expected a response for the clue phase"


async def test_player_that_gives_up_gets_the_fallback_with_its_usage() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = scripted_players(game)
    players[0].usage = TurnUsage(model_id="model-0", input_tokens=10, output_tokens=2)
    players[0].script[0] = RuntimeError("invalid json")
    players[0].script[1:] = [RuntimeError("down")] * len(players[0].script[1:])

    game = await play(game, players=players)

    assert errors(game)[0] == "player failed: invalid json"
    assert game.view_for(0).clues[0].clue is None
    assert players[0].retry_reasons[0] is None
    assert game.tokens_used == 12 * len(players[0].views)
    assert game.phase is GamePhase.DONE


async def test_token_budget_aborts_the_game() -> None:
    game = new_game(token_budget=50)
    usage = TurnUsage(model_id="model", input_tokens=20)
    players = [RandomPlayer(seed=seat.seat, usage=usage) for seat in game.seats]

    game = await play(game, players=players)

    assert game.phase is GamePhase.ABORTED
    assert game.tokens_used == 60


async def test_budget_abort_during_a_parallel_phase_stops_cleanly() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0, token_budget=90)
    players = scripted_players(game)

    for player in players:
        player.usage = TurnUsage(model_id="model", input_tokens=20)

    game = await play(game, players=players)

    # The clue round stays under the budget, the first vote goes over it, and the
    # tokens of the other votes still count.
    assert game.phase is GamePhase.ABORTED
    assert game.events_of_type(VoteCastEvent) == []
    assert game.tokens_used == 20 * 2 * len(game.seats)


@pytest.mark.parametrize("seed", range(5))
async def test_random_players_finish_games_despite_blunders(seed: int) -> None:
    game = new_game(player_count=6, imposter_count=2, seed=seed)
    players = [
        RandomPlayer(seed=seed * 10 + seat.seat, blunder_rate=0.4) for seat in game.seats
    ]

    game = await play(game, players=players)

    assert game.phase is GamePhase.DONE
    assert game.outcome is not None


class SlowPlayer:
    """A scripted player that answers after a delay, to reorder parallel answers.

    Attributes:
        player: The scripted player that gives the answers.
        delay: The seconds to wait before every answer.
    """

    def __init__(self, *, player: ScriptedPlayer, delay: float) -> None:
        self.player = player
        self.delay = delay

    async def take_turn(
        self,
        *,
        ctx: Context,
        view: PlayerView,
        record_usage: UsageRecorder,
        retry_reason: str | None = None,
    ) -> PhaseResponse:
        """Wait, then give the next scripted answer."""
        await asyncio.sleep(self.delay)

        return self.player.respond(view, retry_reason)


async def test_parallel_answers_are_applied_in_seat_order() -> None:
    game = new_game(clue_rounds=1, discussion_rounds=0)
    players = [
        SlowPlayer(player=player, delay=0.01 * (len(game.seats) - seat))
        for seat, player in enumerate(scripted_players(game))
    ]

    game = await play(game, players=players)

    assert [event.seat for event in game.events_of_type(VoteCastEvent)] == [0, 1, 2, 3]


MODEL_IDS = ["gemini-flash", "claude-haiku", "gpt-oss", "gemini-flash-lite"]


def new_request(**options: object) -> GameRequest:
    """Build a seeded request for a four-seat game."""
    players = [PlayerConfig(model_id=model_id) for model_id in MODEL_IDS]
    config = GameConfig.model_validate({"players": players, "seed": 5, **options})

    return GameRequest(config=config)


def engine_events(events: Sequence[Event]) -> list[BaseGameEvent]:
    """Read the engine events from the custom metadata of ADK events, as clients do."""
    return [
        GAME_EVENT_ADAPTER.validate_python(event.custom_metadata[GAME_EVENT_METADATA_KEY])
        for event in events
        if event.custom_metadata and GAME_EVENT_METADATA_KEY in event.custom_metadata
    ]


def request_state(request: GameRequest) -> dict[str, Any]:
    """Build the initial session state of a game."""
    return {REQUEST_STATE_KEY: request.model_dump(mode="json")}


def test_workflow_is_a_loop_of_function_nodes() -> None:
    graph = fake_builder().build().graph

    assert graph is not None
    edges = {(edge.from_node.name, edge.to_node.name, edge.route) for edge in graph.edges}
    assert edges == {
        ("__START__", "setup", None),
        ("setup", "next_turns", None),
        ("next_turns", "play_turn", TURN_ROUTE),
        ("next_turns", "finish", OVER_ROUTE),
        ("play_turn", "apply_turns", None),
        ("apply_turns", "next_turns", None),
    }


async def test_game_from_a_request_streams_every_engine_event_in_order() -> None:
    workflow = fake_builder().build()

    events, state = await run_events(workflow, state=request_state(new_request()))

    game = Game.load(GameSnapshot.model_validate(state[GAME_STATE_KEY]))
    streamed = engine_events(events)
    assert game.game_id == "game-1"
    assert game.phase is GamePhase.DONE
    assert streamed == list(game.events)
    assert [event.seq for event in streamed] == list(range(len(streamed)))
    assert len(game.events_of_type(ReflectionEvent)) == len(game.seats)
    assert {event.author for event in events} == {WORKFLOW_NAME}


async def test_turn_started_events_are_streamed_before_the_players_answer() -> None:
    workflow = fake_builder().build()

    events, _ = await run_events(workflow, state=request_state(new_request()))

    votes = [event for event in engine_events(events) if event.phase is GamePhase.VOTE]
    started = votes[1 : 1 + len(MODEL_IDS)]
    assert [type(event) for event in started] == [TurnStartedEvent] * len(MODEL_IDS)
    assert VoteCastEvent in {type(event) for event in votes[1 + len(MODEL_IDS) :]}


async def test_game_over_the_token_budget_is_aborted() -> None:
    game = await play_workflow(fake_builder(), request=new_request(token_budget=500))

    assert game.phase is GamePhase.ABORTED
    assert "token budget" in game.events_of_type(GameAbortedEvent)[-1].reason


async def test_session_that_has_a_game_does_not_start_another() -> None:
    game = await play_workflow(fake_builder(), request=new_request())

    events, state = await run_events(
        fake_builder().build(),
        state={
            **request_state(new_request(seed=6)),
            GAME_STATE_KEY: game.snapshot().model_dump(mode="json"),
        },
    )

    assert engine_events(events) == []
    assert events[-1].content is not None
    assert state[GAME_STATE_KEY] == game.snapshot().model_dump(mode="json")


async def test_workflow_uses_the_default_request_without_one_in_state() -> None:
    builder = fake_builder(default_request=new_request(clue_rounds=1))

    game = await play_workflow(builder)

    assert game.config.clue_rounds == 1
    assert game.phase is GamePhase.DONE


async def test_workflow_without_any_request_fails() -> None:
    with pytest.raises(ValueError, match="no game request"):
        await run_events(fake_builder().build())


class ObedientLlm(BaseLlm):
    """A model that answers every turn with a clue, statement, vote or guess of its own.

    Attributes:
        requests: The requests the model received, in order.
    """

    model: str = "obedient"
    requests: list[LlmRequest] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.requests.append(llm_request.model_copy(deep=True))
        number = len(self.requests)
        answer = {
            "clue": f"word{number}",
            "statement": f"Statement {number}.",
            "vote_for": "nobody",
            "guess": "zebra",
            "reflection": "Fine.",
            "private_reasoning": f"thought<{self.model}:{number}>",
        }

        text = json.dumps(answer)

        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=5
            ),
        )

    def sent_texts(self) -> list[str]:
        """Join everything each request sent to the model: instructions and messages."""
        return [
            "\n".join(
                [
                    str(request.config.system_instruction),
                    *(
                        part.text or ""
                        for content in request.contents
                        for part in content.parts or []
                    ),
                ]
            )
            for request in self.requests
        ]


async def test_models_are_sent_only_the_view_of_their_seat() -> None:
    catalog = ModelCatalog.load()
    seating = LlmPlayerSeating(catalog)
    models = {model_id: ObedientLlm(model=model_id) for model_id in MODEL_IDS}
    seating.models.update(models)
    builder = fake_builder()
    builder.players = seating
    request = GameRequest(
        config=new_request().config,
        words=WordOptions(mode=WordMode.TYPED, word="giraffe"),
    )

    game = await play_workflow(builder, request=request)

    assert game.phase is GamePhase.DONE
    assert game.tokens_used > 0
    thoughts = {
        event.seat: event.private_reasoning
        for event in game.events_of_type(ClueGivenEvent)
        if event.round == 1
    }

    for seat in game.seats:
        texts = models[seat.player.model_id].sent_texts()
        # The last request of a seat is its debrief, after the word is revealed.
        before_reveal = texts[:-1]
        others = [thought for other, thought in thoughts.items() if other != seat.seat]

        assert thoughts[seat.seat] in texts[-1]
        assert all(other not in text for text in before_reveal for other in others)

        if seat.role is PlayerRole.IMPOSTER:
            assert all("giraffe" not in text.lower() for text in before_reveal)
        else:
            assert all("giraffe" in text.lower() for text in before_reveal)


async def test_generated_word_is_made_by_an_agent_inside_the_game_run(
    flash_lite: ModelCatalogEntry, replay_llm: ReplayLlm
) -> None:
    replay_llm.replies = [
        json.dumps({"word": "dusk", "category": "times of day", "hint": "fading"})
    ]
    builder = fake_builder()
    builder.words = SecretWordResolver(
        picker=WordPicker.load(seed=3),
        generator=WordGenerator(entry=flash_lite, model=replay_llm),
    )
    request = GameRequest(
        config=new_request().config, words=WordOptions(mode=WordMode.GENERATED)
    )

    events, state = await run_events(builder.build(), state=request_state(request))

    game = Game.load(GameSnapshot.model_validate(state[GAME_STATE_KEY]))
    authors = [event.author for event in events]
    assert game.secret.word == "dusk"
    assert game.phase is GamePhase.DONE
    assert authors.index("word_generator") < authors.index(WORKFLOW_NAME)
