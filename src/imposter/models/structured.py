import uuid

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from imposter.models.catalog import ModelCatalogEntry
from imposter.models.factory import adk_model, output_config

APP_NAME = "imposter-tasks"
"""The ADK app name of the one-off structured tasks."""

USER_ID = "imposter"
"""The ADK user of the task sessions."""

ANSWER_STATE_KEY = "answer"
"""The session state key under which ADK stores the validated answer."""


class StructuredTaskAgent[ResponseT: BaseModel]:
    """Runs one-off tasks on an ADK `LlmAgent` with a structured response.

    Used by setup and judging tasks such as the word generator and the LLM judge. Every
    call runs in a fresh session with `include_contents='none'`, so tasks never see each
    other. ADK validates the answer against the response type.

    Attributes:
        entry: The catalog entry of the model.
        response_type: The pydantic model of the answer.
        runner: The ADK runner of the agent.
    """

    def __init__(
        self,
        *,
        name: str,
        entry: ModelCatalogEntry,
        instruction: str,
        response_type: type[ResponseT],
        max_output_tokens: int,
        temperature: float | None = None,
        model: BaseLlm | None = None,
    ) -> None:
        """Initialize the agent and its runner.

        Args:
            name: The ADK agent name.
            entry: The catalog entry of the model.
            instruction: The system instruction of every task.
            response_type: The pydantic model of the answer.
            max_output_tokens: The answer tokens, without the room for thinking.
            temperature: A temperature that overrides the entry's default, if given.
            model: The ADK model object, built from the entry when not given.
        """
        self.entry = entry
        self.response_type = response_type
        agent = LlmAgent(
            name=name,
            model=model or adk_model(entry),
            instruction=instruction,
            include_contents="none",
            output_schema=response_type,
            output_key=ANSWER_STATE_KEY,
            generate_content_config=output_config(
                entry=entry, max_output_tokens=max_output_tokens, temperature=temperature
            ),
        )
        self.runner = Runner(
            app_name=APP_NAME,
            agent=agent,
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )

    async def answer(self, task: str) -> ResponseT:
        """Run one task.

        Args:
            task: The user message of the task.

        Returns:
            The validated answer.

        Raises:
            RuntimeError: When the model gives no valid answer.
        """
        answer = None
        error = None

        async for event in self.runner.run_async(
            user_id=USER_ID,
            session_id=uuid.uuid4().hex,
            new_message=types.Content(role="user", parts=[types.Part(text=task)]),
        ):
            answer = event.actions.state_delta.get(ANSWER_STATE_KEY, answer)
            error = event.error_message or error

        if answer is None:
            message = f"The model {self.entry.id} gave no valid answer: {error}."
            raise RuntimeError(message)

        return self.response_type.model_validate(answer)
