from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context import Context
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.workflow import RetryConfig

from imposter.engine.game import Game
from imposter.engine.responses import PHASE_RESPONSE_TYPES, PhaseResponse
from imposter.engine.views import PlayerView
from imposter.models.catalog import ModelCatalog, ModelCatalogEntry
from imposter.models.factory import adk_model, generate_content_config
from imposter.players.base import TurnUsage, UsageRecorder
from imposter.players.prompt import PlayerPromptRenderer

ANSWER_RETRY = RetryConfig(
    max_attempts=3,
    initial_delay=0.5,
    exceptions=[
        "ValidationError",
        "MidStreamFallbackError",
        "APIConnectionError",
        "Timeout",
    ],
)
"""How ADK retries the agent of a turn: up to three model calls when the answer does not
match the schema or the stream broke off midway. The model client retries only a call
that fails before the first chunk (`models/factory.py`), and other errors are final."""


class ModelResponseError(Exception):
    """Raised when a model answers with an error, or with nothing, instead of content."""


class LlmPlayer:
    """A player backed by a model through a plain ADK `LlmAgent` (README D7, D9).

    Every turn builds one agent and runs it as a child node of the turn node
    (`ctx.run_node`), so the agent's events, including the partial events of a streaming
    run, are part of the game run and its trace. The agent uses
    `include_contents='none'`, so no conversation history is sent: all it knows is the
    instruction rendered from the `PlayerView` of its seat and the task of the phase,
    which is the user message. A fixed `static_instruction` is the system instruction,
    which makes ADK send the rendered instruction as user content: Claude Sonnet refuses
    the game instruction as a system prompt.

    ADK validates the answer against the response type of the phase (`output_schema`)
    and retries the agent as `retry_config` says. Models without native structured
    output get no response schema in the request and are asked for JSON in the task
    instead. Timeouts and retries on rate limits and server errors are part of the
    model client (`models/factory.py`).

    Attributes:
        entry: The catalog entry of the model.
        model: The ADK model object.
        temperature: A temperature that overrides the entry's default, if set.
        renderer: Renders the instruction and the task from the view.
        retry_config: How ADK retries the agent of a turn.
    """

    def __init__(
        self,
        *,
        entry: ModelCatalogEntry,
        model: BaseLlm | None = None,
        temperature: float | None = None,
        renderer: PlayerPromptRenderer | None = None,
        retry_config: RetryConfig = ANSWER_RETRY,
    ) -> None:
        """Initialize the player.

        Args:
            entry: The catalog entry of the model.
            model: The ADK model object, built from the entry when not given.
            temperature: A temperature that overrides the entry's default, if given.
            renderer: Renders the prompts, the default templates when not given.
            retry_config: How ADK retries the agent of a turn.
        """
        self.entry = entry
        self.model = model or adk_model(entry)
        self.temperature = temperature
        self.renderer = renderer or PlayerPromptRenderer()
        self.retry_config = retry_config

    def agent(self, *, view: PlayerView, record_usage: UsageRecorder) -> LlmAgent:
        """Build the agent of one turn.

        The instruction is a provider function instead of a string, because ADK fills
        `{name}` placeholders in a string instruction from session state, and the game
        so far may contain braces.

        Args:
            view: Everything the seat may know.
            record_usage: Takes the tokens of each model call.

        Returns:
            The agent, named `player_{seat}_{phase}`, which is the author of its events.
        """
        instruction = self.renderer.instruction(view)

        def view_instruction(context: ReadonlyContext) -> str:
            return instruction

        def record_response(
            callback_context: CallbackContext, llm_response: LlmResponse
        ) -> None:
            # A streaming call passes each partial response through the callback too.
            if llm_response.partial:
                return

            usage = llm_response.usage_metadata

            if usage is not None:
                record_usage(
                    TurnUsage(
                        model_id=self.entry.id,
                        input_tokens=usage.prompt_token_count or 0,
                        output_tokens=usage.candidates_token_count or 0,
                        thinking_tokens=usage.thoughts_token_count or 0,
                    )
                )

            if llm_response.error_code:
                message = f"{llm_response.error_code}: {llm_response.error_message}"
                raise ModelResponseError(message)

        return LlmAgent(
            name=f"player_{view.seat}_{view.phase}",
            description=f"Plays seat {view.seat} in the {view.phase} phase.",
            model=self.model,
            static_instruction=self.renderer.system(),
            instruction=view_instruction,
            include_contents="none",
            output_schema=PHASE_RESPONSE_TYPES[view.phase],
            generate_content_config=generate_content_config(
                entry=self.entry, phase=view.phase, temperature=self.temperature
            ),
            before_model_callback=(
                None if self.entry.supports_structured_output else drop_schema
            ),
            after_model_callback=record_response,
            retry_config=self.retry_config,
        )

    async def take_turn(
        self,
        *,
        ctx: Context,
        view: PlayerView,
        record_usage: UsageRecorder,
        retry_reason: str | None = None,
    ) -> PhaseResponse:
        """Ask the model for the action of the phase of the view.

        Args:
            ctx: The context of the turn node, which runs the agent as a child node.
            view: Everything the seat may know.
            record_usage: Takes the tokens of each model call of the turn.
            retry_reason: Why the previous attempt in this turn was rejected, if any.

        Returns:
            The answer, validated by ADK against the response type of the phase.

        Raises:
            ModelResponseError: When the model gave no answer.
        """
        task = self.renderer.task(
            view=view,
            retry_reason=retry_reason,
            include_schema=not self.entry.supports_structured_output,
        )
        agent = self.agent(view=view, record_usage=record_usage)
        answer = await ctx.run_node(agent, node_input=task)

        if answer is None:
            message = f"The model {self.entry.id} gave no answer."
            raise ModelResponseError(message)

        return PHASE_RESPONSE_TYPES[view.phase].model_validate(answer)


class LlmPlayerSeating:
    """Seats an `LlmPlayer` with the model of each seat's config.

    Attributes:
        catalog: The models that can play a seat.
        models: The ADK model object of each catalog entry used so far, by id, so the
            turns of a model share one client.
    """

    def __init__(self, catalog: ModelCatalog) -> None:
        """Initialize the seating without models.

        Args:
            catalog: The models that can play a seat.
        """
        self.catalog = catalog
        self.models: dict[str, BaseLlm] = {}

    def player_for(self, *, game: Game, seat: int) -> LlmPlayer:
        """Get the player of a seat, backed by the model of the seat's config.

        Args:
            game: The game.
            seat: The seat.

        Returns:
            The player.

        Raises:
            KeyError: When the model of the seat is not in the catalog.
        """
        entry = self.catalog.entry(game.seats[seat].player.model_id)

        if entry.id not in self.models:
            self.models[entry.id] = adk_model(entry)

        return LlmPlayer(
            entry=entry, model=self.models[entry.id], temperature=game.config.temperature
        )


def drop_schema(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
    """Remove the response schema from a request, a `before_model_callback`.

    Used for models without native structured output: the task asks for JSON instead,
    and ADK still validates the answer against `output_schema`.

    Args:
        callback_context: The ADK context of the call.
        llm_request: The request about to be sent, changed in place.
    """
    llm_request.config.response_schema = None
    llm_request.config.response_mime_type = None
