from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ConfigDict, ValidationError

from imposter.config import GamePhase
from imposter.engine.views import PlayerView
from imposter.models.catalog import ModelCatalogEntry
from imposter.models.factory import adk_model, generate_content_config
from imposter.players.base import PHASE_RESPONSE_TYPES, PlayerResponse, TurnUsage
from imposter.players.prompt import PlayerPromptRenderer
from imposter.utils.retry import call_with_retries
from imposter.utils.text import json_object_text

APP_NAME = "imposter"
"""The ADK app name of the player runners."""

USER_ID = "imposter"
"""The ADK user of the player sessions, one session per game."""

PARSE_ATTEMPTS = 2
"""Model calls per turn: the first answer plus one retry when it is not valid JSON."""


class ModelReply(BaseModel):
    """The text of one model answer and the tokens it used.

    Attributes:
        text: The answer text, without thoughts.
        usage: The tokens the call used.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    usage: TurnUsage


class ModelReplyError(Exception):
    """Raised when the model answers with an error instead of content.

    Attributes:
        code: The error code of the model, for retry decisions.
    """

    def __init__(self, *, code: int | str | None, message: str) -> None:
        """Initialize the error.

        Args:
            code: The error code of the model.
            message: The error message.
        """
        super().__init__(message)
        self.code = code


class AdkPlayer:
    """A player backed by a model through an ADK `LlmAgent` (README D7, D9).

    There is one `LlmAgent` per phase, because the response schema and output limit
    differ per phase. Every agent uses `include_contents='none'`, so no conversation
    history is sent: the instruction is rendered from the seat's `PlayerView` only. The
    view is handed to the instruction provider in session state under
    `player:{seat}:view`, and the task of the phase is the user message. A fixed
    `static_instruction` is the system instruction, which makes ADK send the rendered
    instruction as user content: Claude Sonnet refuses the game instruction as a system
    prompt.

    Models with `supports_structured_output` get the response type as `output_schema`.
    Others are asked for JSON in the task. Either way the answer is validated with
    pydantic, and an invalid answer is retried once with the error. Each model call has
    a timeout and retries transient errors with backoff. When no valid answer comes, the
    response has no output and an error, so the runner applies the phase fallback.

    Attributes:
        entry: The catalog entry of the model.
        seat: The seat this player plays.
        model: The ADK model object.
        renderer: Renders the instruction and task from the view.
        session_service: Stores the ADK sessions, one per game.
        agents: The agent of each phase in which players act.
        timeout_seconds: The time limit of one model call.
        max_retries: The retries of a model call after a transient error.
        backoff_seconds: The base wait before the first retry.
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
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        """Initialize the player and its agents.

        Args:
            entry: The catalog entry of the model.
            seat: The seat this player plays.
            model: The ADK model object, built from the entry when not given.
            temperature: A temperature that overrides the entry's default, if given.
            renderer: Renders the prompts, the default templates when not given.
            session_service: Stores the ADK sessions, in memory when not given.
            timeout_seconds: The time limit of one model call.
            max_retries: The retries of a model call after a transient error.
            backoff_seconds: The base wait before the first retry.
        """
        self.entry = entry
        self.seat = seat
        self.model = model or adk_model(entry)
        self.renderer = renderer or PlayerPromptRenderer()
        self.session_service = session_service or InMemorySessionService()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.agents = {
            phase: self.agent_for(phase=phase, temperature=temperature)
            for phase in PHASE_RESPONSE_TYPES
        }

    @property
    def view_state_key(self) -> str:
        """The session state key under which the view is handed to the agent."""
        return f"player:{self.seat}:view"

    def agent_for(self, *, phase: GamePhase, temperature: float | None) -> LlmAgent:
        """Build the agent of one phase.

        Args:
            phase: The phase.
            temperature: A temperature that overrides the entry's default, if given.

        Returns:
            The agent, with the response type as output schema when the model supports
            it.
        """
        return LlmAgent(
            name=f"player_{self.seat}_{phase}",
            description=f"Plays seat {self.seat} in the {phase} phase.",
            model=self.model,
            static_instruction=self.renderer.system(),
            instruction=self.instruction,
            include_contents="none",
            output_schema=(
                PHASE_RESPONSE_TYPES[phase]
                if self.entry.supports_structured_output
                else None
            ),
            generate_content_config=generate_content_config(
                entry=self.entry, phase=phase, temperature=temperature
            ),
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
        if view.seat != self.seat or view.phase not in self.agents:
            message = (
                f"Player of seat {self.seat} cannot act on the view of seat {view.seat} "
                f"in phase {view.phase}."
            )
            raise ValueError(message)

        response_type = PHASE_RESPONSE_TYPES[view.phase]
        usages: list[TurnUsage] = []
        reason = retry_reason

        for _ in range(PARSE_ATTEMPTS):
            try:
                reply = await call_with_retries(
                    lambda reason=reason: self.reply(view=view, retry_reason=reason),
                    timeout_seconds=self.timeout_seconds,
                    max_retries=self.max_retries,
                    backoff_seconds=self.backoff_seconds,
                )
            except Exception as error:
                return PlayerResponse(
                    output=None,
                    usage=self.total_usage(usages),
                    error=f"model call failed: {type(error).__name__}: {error}",
                )

            usages.append(reply.usage)

            try:
                output = response_type.model_validate_json(json_object_text(reply.text))
            except ValidationError as error:
                reason = self.validation_reason(error)
                continue

            return PlayerResponse(output=output, usage=self.total_usage(usages))

        return PlayerResponse(
            output=None,
            usage=self.total_usage(usages),
            error=f"invalid answer, falling back: {reason}",
        )

    async def reply(self, *, view: PlayerView, retry_reason: str | None) -> ModelReply:
        """Call the model once through the ADK runner of the phase.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt in this turn was rejected, if any.

        Returns:
            The answer text and the tokens used.

        Raises:
            ModelReplyError: When the model answers with an error.
        """
        runner = Runner(
            app_name=APP_NAME,
            agent=self.agents[view.phase],
            session_service=self.session_service,
            auto_create_session=True,
        )
        task = self.renderer.task(
            view=view,
            retry_reason=retry_reason,
            include_schema=not self.entry.supports_structured_output,
        )
        message = types.Content(role="user", parts=[types.Part(text=task)])
        text = ""
        input_tokens = output_tokens = thinking_tokens = 0

        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=view.game_id,
            new_message=message,
            state_delta={self.view_state_key: view.model_dump(mode="json")},
        ):
            if event.error_code:
                raise ModelReplyError(
                    code=event.error_code,
                    message=f"The model answered with error {event.error_code}: "
                    f"{event.error_message}.",
                )

            usage = event.usage_metadata

            if usage is not None:
                input_tokens += usage.prompt_token_count or 0
                output_tokens += usage.candidates_token_count or 0
                thinking_tokens += usage.thoughts_token_count or 0

            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(
                    part.text
                    for part in event.content.parts
                    if part.text and not part.thought
                )

        return ModelReply(
            text=text,
            usage=TurnUsage(
                model_id=self.entry.id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
            ),
        )

    def total_usage(self, usages: list[TurnUsage]) -> TurnUsage | None:
        """Add up the tokens of the model calls of one turn.

        Args:
            usages: The usage of each call.

        Returns:
            The total, or `None` when no call returned.
        """
        if not usages:
            return None

        return TurnUsage(
            model_id=self.entry.id,
            input_tokens=sum(usage.input_tokens for usage in usages),
            output_tokens=sum(usage.output_tokens for usage in usages),
            thinking_tokens=sum(usage.thinking_tokens for usage in usages),
        )

    def validation_reason(self, error: ValidationError) -> str:
        """Describe a validation error as a retry reason the model can act on.

        Args:
            error: The error of parsing the answer.

        Returns:
            The reason, naming each invalid field and the problem.
        """
        problems = [
            f"{'.'.join(str(part) for part in issue['loc']) or 'answer'}: {issue['msg']}"
            for issue in error.errors(include_url=False)
        ]

        return "the answer was not a valid JSON object (" + ", ".join(problems) + ")"
