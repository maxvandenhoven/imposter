"""The player turn agents of the evals and the view they play.

Each player eval app (`player_clue/`, `player_discussion/`, `player_debrief/`) exposes
`player_eval_agent(phase)` as its `root_agent`: a clone of the production agent of that
phase of `AdkPlayer`, with the same model, static instruction, response schema,
generation config and callbacks. Only where the turn comes from differs. In a game the
player renders its prompts from the view of the current turn, here they are rendered
from the view in the session state of the eval case, with the same templates.

The view of a case was logged in a past game. `case_view` applies the current default
caps of `GameConfig` to it, so that a change of the defaults is evaluated without
rebuilding the eval sets. The metrics read the view through the same function.

The model is the catalog id in `IMPOSTER_EVAL_MODEL`, `gemini-flash` by default.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models import LlmRequest
from google.genai import types

from imposter.config import GameConfig, GamePhase
from imposter.engine.views import PlayerView
from imposter.models.catalog import ModelCatalog
from imposter.players.adk_player import AdkPlayer

MODEL_ID = os.environ.get("IMPOSTER_EVAL_MODEL", "gemini-flash")
"""The catalog id of the model under test."""

VIEW_STATE_KEY = "view"
"""The session state key of the `PlayerView` of the case."""

DEFAULT_CAPS = {
    field: GameConfig.model_fields[field].default
    for field in ("statement_word_cap", "reasoning_word_cap")
}
"""The default word caps of `GameConfig`, which the cases are played with."""


def case_view(view: PlayerView) -> PlayerView:
    """Apply the current default word caps to the view of a case.

    Args:
        view: The view as it was logged.

    Returns:
        The view with the statement and reasoning caps of `GameConfig` defaults.
    """
    rules = view.rules.model_copy(update=DEFAULT_CAPS)

    return view.model_copy(update={"rules": rules})


def state_view(context: ReadonlyContext) -> PlayerView:
    """Read the view of the eval case from the session state.

    Args:
        context: The ADK context of the call.

    Returns:
        The view, with the current default caps.
    """
    return case_view(PlayerView.model_validate(context.state[VIEW_STATE_KEY]))


def player_eval_agent(phase: GamePhase) -> LlmAgent:
    """Build the eval agent of one phase: the production agent, fed from the state.

    Args:
        phase: The phase.

    Returns:
        The agent.
    """
    player = AdkPlayer(entry=ModelCatalog.load().entry(MODEL_ID), seat=0)
    renderer = player.renderer

    def instruction(context: ReadonlyContext) -> str:
        """Render the instruction of the turn, an instruction provider.

        Args:
            context: The ADK context, whose state holds the view.

        Returns:
            The instruction.
        """
        return renderer.instruction(state_view(context))

    def render_task(
        *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> None:
        """Send the task of the turn instead of the case's message, a callback.

        Args:
            callback_context: The ADK context, whose state holds the view.
            llm_request: The request about to be sent, changed in place.
        """
        task = renderer.task(
            view=state_view(callback_context),
            include_schema=not player.entry.supports_structured_output,
        )
        # ADK sends the rendered instruction as a user message before the message of
        # the case, because the agent has a static instruction, so only the last one is
        # replaced.
        llm_request.contents[-1] = types.Content(
            role="user", parts=[types.Part(text=task)]
        )

    agent = player.agents[phase]
    callbacks = [agent.before_model_callback] if agent.before_model_callback else []

    return agent.clone(
        update={
            "name": f"player_{phase}",
            "instruction": instruction,
            "before_model_callback": [render_task, *callbacks],
        }
    )
