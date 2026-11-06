import json
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from judge_clue.agent import root_agent as judge_agent
from player_clue.agent import root_agent as player_agent
from player_debrief.agent import root_agent as debrief_agent
from player_discussion.agent import root_agent as discussion_agent
from player_turn import DEFAULT_CAPS, case_view

from imposter.config import GamePhase
from imposter.engine.views import PlayerView
from imposter.judge.llm_judge import JUDGE_INSTRUCTION, JudgeAnswer
from imposter.players.base import PHASE_RESPONSE_TYPES
from imposter.players.prompt import PlayerPromptRenderer


def request_text(content: types.Content) -> str:
    return "".join(part.text or "" for part in content.parts or [])


def test_the_judge_eval_agent_is_the_production_judge_agent() -> None:
    assert isinstance(judge_agent, LlmAgent)
    assert judge_agent.instruction == JUDGE_INSTRUCTION
    assert judge_agent.output_schema is JudgeAnswer


async def test_the_player_eval_agent_sends_the_prompts_of_the_view_in_the_state(
    civilian_clue_view: PlayerView, replay_llm: Any
) -> None:
    model = replay_llm
    model.replies = [json.dumps({"clue": "tall", "private_reasoning": "x"})]
    agent = player_agent.clone(update={"model": model})
    runner = Runner(
        app_name="player_clue", agent=agent, session_service=InMemorySessionService()
    )
    session = await runner.session_service.create_session(
        app_name="player_clue",
        user_id="eval",
        state={"view": civilian_clue_view.model_dump(mode="json")},
    )
    renderer = PlayerPromptRenderer()

    events = [
        event
        async for event in runner.run_async(
            user_id="eval",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="Stale task.")]
            ),
        )
    ]

    contents = [request_text(content) for content in model.requests[0].contents]
    assert renderer.instruction(civilian_clue_view) in contents[0]
    assert contents[-1] == renderer.task(view=civilian_clue_view)
    assert "Stale task." not in "".join(contents)
    assert events[-1].content is not None
    assert json.loads(request_text(events[-1].content))["clue"] == "tall"


def test_each_player_app_plays_the_agent_of_its_phase() -> None:
    agents = {
        GamePhase.CLUE: player_agent,
        GamePhase.DISCUSSION: discussion_agent,
        GamePhase.DEBRIEF: debrief_agent,
    }

    for phase, agent in agents.items():
        assert agent.name == f"player_{phase}"
        assert agent.output_schema is PHASE_RESPONSE_TYPES[phase]


def test_a_case_is_played_with_the_current_default_caps(
    civilian_clue_view: PlayerView,
) -> None:
    rules = civilian_clue_view.rules.model_copy(
        update={"reasoning_word_cap": 7, "statement_word_cap": 9}
    )
    logged = civilian_clue_view.model_copy(update={"rules": rules})

    view = case_view(logged)

    assert view.rules.reasoning_word_cap == DEFAULT_CAPS["reasoning_word_cap"]
    assert view.rules.statement_word_cap == DEFAULT_CAPS["statement_word_cap"]
    assert view.rules.clue_rounds == civilian_clue_view.rules.clue_rounds
