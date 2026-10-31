from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context import Context
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from pydantic import BaseModel, ConfigDict

from imposter.config import GamePhase
from imposter.engine.views import PlayerView
from imposter.models.catalog import ModelCatalogEntry
from imposter.models.factory import adk_model, generate_content_config
from imposter.players.base import PHASE_RESPONSE_TYPES, PlayerResponse, TurnUsage
from imposter.players.prompt import PlayerPromptRenderer

ANSWER_ATTEMPTS = 2
"""Model calls per turn: the first answer plus one retry when it does not match the
schema."""

SCHEMA_ERROR_CODE = "ValidationError"
"""The error code of an answer that does not match the schema."""

NO_ANSWER_ERROR_CODE = "NoAnswer"
"""The error code of a run that ended without an answer or an error of the model."""


class ModelAnswer(BaseModel):
    """What one run of a phase agent produced.

    Attributes:
        answer: The answer, validated by ADK against the phase's response type, or
            `None` when there is none.
        error_code: The code of the error, if the run failed.
        error_message: The message of the error, if the run failed.
    """

    model_config = ConfigDict(frozen=True)

    answer: dict[str, Any] | None
    error_code: str | None = None
    error_message: str | None = None


class AdkPlayer:
    """A player backed by a model through ADK `LlmAgent`s (README D7, D9).

    Each phase has its own agent, because ADK takes the response type only as
    `output_schema`. A turn runs the agent of its phase as a child node of the turn node
    (`ctx.run_node`), so the agent's events, including the partial events of a streaming
    run, are part of the game run and its trace. The agents use
    `include_contents='none'`, so no conversation history is sent. The instruction
    provider renders the instruction from the `PlayerView` of the current turn, and the
    task of the phase is the user message. A fixed `static_instruction` is the system
    instruction, which makes ADK send the rendered instruction as user content: Claude
    Sonnet refuses the game instruction as a system prompt.

    ADK validates the answer against the response type. Models without native
    structured output get no response schema in the request and are asked for JSON in
    the task instead. An answer that does not match the schema is asked again once with
    the error. Timeouts and retries on rate limits and server errors are part of the
    model client (`models/factory.py`). When no valid answer comes, the response has no
    output and an error, so the runner applies the phase fallback.

    Attributes:
        entry: The catalog entry of the model.
        seat: The seat this player plays.
        model: The ADK model object, shared by the agents of all phases.
        renderer: Renders the instructions and tasks from the view.
        agents: The ADK agent of each phase in which players act.
        view: The view of the current turn, which the instruction is rendered from. A
            seat takes one turn at a time.
        usages: The tokens of each model call of the current turn, recorded by an
            `after_model_callback`.
        failed_response: The last model response of the current turn that came with an
            error, recorded by the same callback. Only a schema error, which comes
            without one, asks the model again.
    """

    def __init__(
        self,
        *,
        entry: ModelCatalogEntry,
        seat: int,
        model: BaseLlm | None = None,
        temperature: float | None = None,
        renderer: PlayerPromptRenderer | None = None,
    ) -> None:
        """Initialize the player and its agents.

        Args:
            entry: The catalog entry of the model.
            seat: The seat this player plays.
            model: The ADK model object, built from the entry when not given.
            temperature: A temperature that overrides the entry's default, if given.
            renderer: Renders the prompts, the default templates when not given.
        """
        self.entry = entry
        self.seat = seat
        self.model = model or adk_model(entry)
        self.renderer = renderer or PlayerPromptRenderer()
        self.view: PlayerView | None = None
        self.usages: list[TurnUsage] = []
        self.failed_response: LlmResponse | None = None
        self.agents = {
            phase: self.agent_for(phase=phase, temperature=temperature)
            for phase in PHASE_RESPONSE_TYPES
        }

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
            generate_content_config=generate_content_config(
                entry=self.entry, phase=phase, temperature=temperature
            ),
            before_model_callback=(
                None if self.entry.supports_structured_output else self.drop_schema
            ),
            after_model_callback=self.record_response,
        )

    def instruction(self, context: ReadonlyContext) -> str:
        """Render the instruction from the view of the turn, an instruction provider.

        Args:
            context: The ADK context of the call, unused.

        Returns:
            The instruction.

        Raises:
            RuntimeError: When no turn is being taken.
        """
        if self.view is None:
            message = f"Player of seat {self.seat} has no turn to render."
            raise RuntimeError(message)

        return self.renderer.instruction(self.view)

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

    def record_response(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> None:
        """Record the tokens and the error of a model call, an `after_model_callback`.

        A streaming call also passes each partial response through the callback, and
        those can carry the usage so far, so only the final response counts. It runs
        before ADK validates the answer, so calls with an invalid answer count.

        Args:
            callback_context: The ADK context of the call.
            llm_response: The response of the model.
        """
        if llm_response.partial:
            return

        if llm_response.error_code:
            self.failed_response = llm_response

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
        self,
        view: PlayerView,
        retry_reason: str | None = None,
        ctx: Context | None = None,
    ) -> PlayerResponse:
        """Ask the model for the action of the phase of the view.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt in this turn was rejected, if any.
            ctx: The context of the turn node, which runs the agent as a child node.

        Returns:
            The validated output and the tokens used, or no output and an error when the
            model gave no valid answer.

        Raises:
            ValueError: When the view is of another seat or of a phase without actions,
                or there is no node context.
        """
        if view.seat != self.seat or view.phase not in self.agents:
            message = (
                f"Player of seat {self.seat} cannot act on the view of seat {view.seat} "
                f"in phase {view.phase}."
            )
            raise ValueError(message)

        if ctx is None:
            message = f"Player of seat {self.seat} takes turns only in a workflow node."
            raise ValueError(message)

        self.view = view
        self.usages = []
        self.failed_response = None
        reason = retry_reason
        error = ""

        for _ in range(ANSWER_ATTEMPTS):
            result = await self.ask_model(ctx=ctx, view=view, retry_reason=reason)

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
        self, *, ctx: Context, view: PlayerView, retry_reason: str | None
    ) -> ModelAnswer:
        """Run the agent of the view's phase once, as a child node of the turn node.

        Args:
            ctx: The context of the turn node.
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

        # A failed child node raises an error that wraps the error of the node, such as
        # the validation error of an answer that misses the schema, in `error`.
        try:
            answer = await ctx.run_node(self.agents[view.phase], node_input=task)
        except Exception as failure:
            error = getattr(failure, "error", failure)
            status = getattr(error, "status", None)

            return ModelAnswer(
                answer=None,
                error_code=status if isinstance(status, str) else type(error).__name__,
                error_message=str(error),
            )

        if answer is None:
            failed = self.failed_response

            return ModelAnswer(
                answer=None,
                error_code=failed.error_code if failed else NO_ANSWER_ERROR_CODE,
                error_message=failed.error_message if failed else "No answer came.",
            )

        return ModelAnswer(answer=answer)

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
