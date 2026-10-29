from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ConfigDict

from imposter.config import GamePhase
from imposter.engine.views import PlayerView
from imposter.models.catalog import ModelCatalogEntry
from imposter.models.factory import adk_model, generate_content_config
from imposter.players.base import PHASE_RESPONSE_TYPES, PlayerResponse, TurnUsage
from imposter.players.prompt import PlayerPromptRenderer

APP_NAME = "imposter"
"""The ADK app name of the player runners."""

USER_ID = "imposter"
"""The ADK user of the player sessions, one session per game and phase."""

ANSWER_ATTEMPTS = 2
"""Model calls per turn: the first answer plus one retry when it does not match the
schema."""

SCHEMA_ERROR_CODE = "ValidationError"
"""The error code of the event ADK yields for an answer that does not match the schema."""


class ModelAnswer(BaseModel):
    """What one run of a phase agent produced.

    Attributes:
        answer: The answer, validated by ADK against the phase's response type, or
            `None` when there is none.
        error_code: The code of the error event, if the run failed.
        error_message: The message of the error event, if the run failed.
    """

    model_config = ConfigDict(frozen=True)

    answer: dict[str, Any] | None
    error_code: str | None = None
    error_message: str | None = None


class AdkPlayer:
    """A player backed by a model through ADK `LlmAgent`s (README D7, D9).

    Each phase has its own agent, because ADK takes the response type only as
    `output_schema`. The agents use `include_contents='none'`, so no conversation
    history is sent. The instruction provider renders the instruction from the
    `PlayerView` that the call puts in session state, and the task of the phase is the
    user message. A fixed `static_instruction` is the system instruction, which makes ADK
    send the rendered instruction as user content: Claude Sonnet refuses the game
    instruction as a system prompt.

    ADK validates the answer against the response type and stores it in session state
    (`output_key`). Models without native structured output get no response schema in
    the request and are asked for JSON in the task instead. An answer that does not
    match the schema is asked again once with the error. Timeouts and retries on rate
    limits and server errors are part of the model client (`models/factory.py`). When no
    valid answer comes, the response has no output and an error, so the runner applies
    the phase fallback.

    Attributes:
        entry: The catalog entry of the model.
        seat: The seat this player plays.
        model: The ADK model object, shared by the agents of all phases.
        renderer: Renders the instructions and tasks from the view.
        runners: The ADK runner of each phase in which players act.
        usages: The tokens of each model call of the current turn, recorded by an
            `after_model_callback`. A seat takes one turn at a time.
    """

    def __init__(
        self,
        *,
        entry: ModelCatalogEntry,
        seat: int,
        model: BaseLlm | None = None,
        temperature: float | None = None,
        renderer: PlayerPromptRenderer | None = None,
        session_service: BaseSessionService | None = None,
    ) -> None:
        """Initialize the player and its agents.

        Args:
            entry: The catalog entry of the model.
            seat: The seat this player plays.
            model: The ADK model object, built from the entry when not given.
            temperature: A temperature that overrides the entry's default, if given.
            renderer: Renders the prompts, the default templates when not given.
            session_service: Stores the ADK sessions, in memory when not given.
        """
        self.entry = entry
        self.seat = seat
        self.model = model or adk_model(entry)
        self.renderer = renderer or PlayerPromptRenderer()
        self.usages: list[TurnUsage] = []
        sessions = session_service or InMemorySessionService()
        self.runners = {
            phase: Runner(
                app_name=APP_NAME,
                agent=self.agent_for(phase=phase, temperature=temperature),
                session_service=sessions,
                auto_create_session=True,
            )
            for phase in PHASE_RESPONSE_TYPES
        }

    @property
    def view_state_key(self) -> str:
        """The session state key under which the view is handed to the agent."""
        return f"player:{self.seat}:view"

    @property
    def answer_state_key(self) -> str:
        """The session state key under which ADK stores the validated answer."""
        return f"player:{self.seat}:answer"

    def agent_for(self, *, phase: GamePhase, temperature: float | None) -> LlmAgent:
        """Build the agent of one phase.

        Args:
            phase: The phase.
            temperature: A temperature that overrides the entry's default, if given.

        Returns:
            The agent.
        """
        return LlmAgent(
            name=f"player_{self.seat}_{phase}",
            description=f"Plays seat {self.seat} in the {phase} phase.",
            model=self.model,
            static_instruction=self.renderer.system(),
            instruction=self.instruction,
            include_contents="none",
            output_schema=PHASE_RESPONSE_TYPES[phase],
            output_key=self.answer_state_key,
            generate_content_config=generate_content_config(
                entry=self.entry, phase=phase, temperature=temperature
            ),
            before_model_callback=(
                None if self.entry.supports_structured_output else self.drop_schema
            ),
            after_model_callback=self.record_usage,
        )

    def instruction(self, context: ReadonlyContext) -> str:
        """Render the instruction from the view in session state (instruction provider).

        Args:
            context: The ADK context of the call.

        Returns:
            The instruction.
        """
        view = PlayerView.model_validate(context.state[self.view_state_key])

        return self.renderer.instruction(view)

    def drop_schema(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> None:
        """Remove the response schema from the request, a `before_model_callback`.

        Used for models without native structured output: the task asks for JSON
        instead, and ADK still validates the answer against `output_schema`.

        Args:
            callback_context: The ADK context of the call.
            llm_request: The request about to be sent, changed in place.
        """
        llm_request.config.response_schema = None
        llm_request.config.response_mime_type = None

    def record_usage(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> None:
        """Record the tokens of a model call, an `after_model_callback`.

        It runs before ADK validates the answer, so calls with an invalid answer count.

        Args:
            callback_context: The ADK context of the call.
            llm_response: The response of the model.
        """
        usage = llm_response.usage_metadata

        if usage is None:
            return

        self.usages.append(
            TurnUsage(
                model_id=self.entry.id,
                input_tokens=usage.prompt_token_count or 0,
                output_tokens=usage.candidates_token_count or 0,
                thinking_tokens=usage.thoughts_token_count or 0,
            )
        )

    async def take_turn(
        self, view: PlayerView, retry_reason: str | None = None
    ) -> PlayerResponse:
        """Ask the model for the action of the phase of the view.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt in this turn was rejected, if any.

        Returns:
            The validated output and the tokens used, or no output and an error when the
            model gave no valid answer.

        Raises:
            ValueError: When the view is of another seat or of a phase without actions.
        """
        if view.seat != self.seat or view.phase not in self.runners:
            message = (
                f"Player of seat {self.seat} cannot act on the view of seat {view.seat} "
                f"in phase {view.phase}."
            )
            raise ValueError(message)

        self.usages = []
        reason = retry_reason
        error = ""

        for _ in range(ANSWER_ATTEMPTS):
            result = await self.ask_model(view=view, retry_reason=reason)

            if result.answer is not None:
                output = PHASE_RESPONSE_TYPES[view.phase].model_validate(result.answer)
                return PlayerResponse(output=output, usage=self.total_usage())

            error = f"{result.error_code}: {result.error_message}"

            if result.error_code != SCHEMA_ERROR_CODE:
                break

            reason = f"the answer did not match the JSON schema ({result.error_message})"

        return PlayerResponse(
            output=None, usage=self.total_usage(), error=f"no valid answer: {error}"
        )

    async def ask_model(
        self, *, view: PlayerView, retry_reason: str | None
    ) -> ModelAnswer:
        """Run the agent of the view's phase once.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt in this turn was rejected, if any.

        Returns:
            The validated answer, or the error of the run.
        """
        task = self.renderer.task(
            view=view,
            retry_reason=retry_reason,
            include_schema=not self.entry.supports_structured_output,
        )
        answer = error_code = error_message = None

        # A failed run yields an error event and then raises, so the error is already
        # known when the exception arrives. Each phase has a session of its own, because
        # ADK warns about events in a session from agents its runner does not know.
        try:
            async for event in self.runners[view.phase].run_async(
                user_id=USER_ID,
                session_id=f"{view.game_id}-{view.phase}",
                new_message=types.Content(role="user", parts=[types.Part(text=task)]),
                state_delta={self.view_state_key: view.model_dump(mode="json")},
            ):
                answer = event.actions.state_delta.get(self.answer_state_key, answer)
                error_code = event.error_code or error_code
                error_message = event.error_message or error_message
        except Exception as error:
            error_code = error_code or type(error).__name__
            error_message = error_message or str(error)

        return ModelAnswer(
            answer=answer, error_code=error_code, error_message=error_message
        )

    def total_usage(self) -> TurnUsage:
        """Add up the tokens of the model calls of the current turn.

        Returns:
            The total.
        """
        return TurnUsage(
            model_id=self.entry.id,
            input_tokens=sum(usage.input_tokens for usage in self.usages),
            output_tokens=sum(usage.output_tokens for usage in self.usages),
            thinking_tokens=sum(usage.thinking_tokens for usage in self.usages),
        )
