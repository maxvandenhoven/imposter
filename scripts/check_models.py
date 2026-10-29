"""Check which candidate models answer on Vertex AI in the project.

Sends one tiny prompt to each candidate model: Gemini through `google-genai`, Claude and
open models through LiteLLM (`vertex_ai/...`), the same routes the players use. Each model
is tried at location `global` first and at a regional fallback location if that fails.
Prints one line per model with OK or the error.

Exits with 0 when at least one Gemini and one Claude model answer, otherwise 1.

Usage: `uv run python scripts/check_models.py [--project ID] [--model ID ...]`. The
project defaults to `GOOGLE_CLOUD_PROJECT`; credentials come from ADC (`gcloud auth
application-default login`).
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

import typer

GLOBAL_LOCATION = "global"
PROMPT = "Reply with the single word OK."
MAX_OUTPUT_TOKENS = 1024
MAX_DETAIL_LENGTH = 200

logger = logging.getLogger("check_models")


class ModelFamily(StrEnum):
    """The model families of the starting lineup and how they are called."""

    GEMINI = "gemini"
    CLAUDE = "claude"
    OPEN = "open"


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """A Vertex AI model to check.

    Attributes:
        model_id: The Vertex AI model ID, without the LiteLLM `vertex_ai/` prefix.
        family: The model family, which decides the client library.
    """

    model_id: str
    family: ModelFamily

    def ping(self, project: str, location: str) -> str:
        """Send the prompt to the model and return its reply.

        Args:
            project: The GCP project ID to call the model in.
            location: The Vertex AI location, `global` or a region.

        Returns:
            The reply text, stripped.
        """
        if self.family is ModelFamily.GEMINI:
            return self.ping_genai(project=project, location=location)

        return self.ping_litellm(project=project, location=location)

    def ping_genai(self, project: str, location: str) -> str:
        """Send the prompt through the `google-genai` client.

        Args:
            project: The GCP project ID to call the model in.
            location: The Vertex AI location, `global` or a region.

        Returns:
            The reply text, stripped.
        """
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=self.model_id,
            contents=PROMPT,
            config=types.GenerateContentConfig(max_output_tokens=MAX_OUTPUT_TOKENS),
        )
        return (response.text or "").strip()

    def ping_litellm(self, project: str, location: str) -> str:
        """Send the prompt through LiteLLM's Vertex AI provider.

        Args:
            project: The GCP project ID to call the model in.
            location: The Vertex AI location, `global` or a region.

        Returns:
            The reply text, stripped.
        """
        import litellm
        from litellm.types.utils import Choices, ModelResponse

        litellm.suppress_debug_info = True
        response = litellm.completion(
            model=f"vertex_ai/{self.model_id}",
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=MAX_OUTPUT_TOKENS,
            vertex_project=project,
            vertex_location=location,
        )
        choice = response.choices[0] if isinstance(response, ModelResponse) else None

        if not isinstance(choice, Choices):
            message = f"Unexpected LiteLLM response: {type(response).__name__}"
            raise TypeError(message)

        return (choice.message.content or "").strip()

    def check(self, project: str, fallback_location: str) -> "ModelCheckResult":
        """Ping the model at `global`, then at the fallback location if that fails.

        Args:
            project: The GCP project ID to call the model in.
            fallback_location: The regional location to try when `global` fails.

        Returns:
            The result with the first location that answered, or the errors of all.
        """
        errors = []

        for location in dict.fromkeys((GLOBAL_LOCATION, fallback_location)):
            try:
                reply = self.ping(project=project, location=location)
            except Exception as error:
                detail = f"{type(error).__name__}: {error}".replace("\n", " ")
                errors.append(f"{location}: {detail[:MAX_DETAIL_LENGTH]}")
                continue

            return ModelCheckResult(
                candidate=self, ok=True, location=location, detail=repr(reply[:40])
            )

        return ModelCheckResult(
            candidate=self, ok=False, location=None, detail=" | ".join(errors)
        )


@dataclass(frozen=True, slots=True)
class ModelCheckResult:
    """The outcome of checking one candidate model.

    Attributes:
        candidate: The checked model.
        ok: Whether the model answered in some location.
        location: The location that answered, `None` when none did.
        detail: The reply when the model answered, otherwise the errors per location.
    """

    candidate: ModelCandidate
    ok: bool
    location: str | None
    detail: str

    def __str__(self) -> str:
        """Format the result as one aligned line."""
        status = "OK  " if self.ok else "FAIL"
        family = self.candidate.family.value
        location = self.location or "-"
        return (
            f"{status} {family:<6} {self.candidate.model_id:<48} {location:<12} "
            f"{self.detail}"
        )


@dataclass(frozen=True, slots=True)
class ModelCheckReport:
    """The results of checking a list of candidate models.

    Attributes:
        results: One result per candidate, in candidate order.
    """

    results: list[ModelCheckResult]

    @classmethod
    def run(
        cls, candidates: Iterable[ModelCandidate], project: str, fallback_location: str
    ) -> "ModelCheckReport":
        """Check each candidate in turn, logging each result as it arrives.

        Args:
            candidates: The models to check.
            project: The GCP project ID to call the models in.
            fallback_location: The regional location to try when `global` fails.

        Returns:
            The report with one result per candidate.
        """
        results = []

        for candidate in candidates:
            result = candidate.check(project=project, fallback_location=fallback_location)
            logger.info("%s", result)
            results.append(result)

        return cls(results=results)

    @property
    def passed(self) -> bool:
        """Whether at least one Gemini and one Claude model answered."""
        ok_families = {result.candidate.family for result in self.results if result.ok}
        return {ModelFamily.GEMINI, ModelFamily.CLAUDE} <= ok_families


# Candidates for the starting lineup, verified with this script. Open MaaS model IDs carry
# the publisher prefix and the `-maas` suffix.
CANDIDATES = [
    ModelCandidate(model_id="gemini-3.1-pro-preview", family=ModelFamily.GEMINI),
    ModelCandidate(model_id="gemini-3.8-flash", family=ModelFamily.GEMINI),
    ModelCandidate(model_id="gemini-3.5-flash-lite", family=ModelFamily.GEMINI),
    ModelCandidate(model_id="claude-sonnet-5-5", family=ModelFamily.CLAUDE),
    ModelCandidate(model_id="claude-haiku-5-5", family=ModelFamily.CLAUDE),
    ModelCandidate(model_id="deepseek-ai/deepseek-v3.2-maas", family=ModelFamily.OPEN),
    ModelCandidate(
        model_id="qwen/qwen3-235b-a22b-instruct-2507-maas", family=ModelFamily.OPEN
    ),
    ModelCandidate(model_id="openai/gpt-oss-120b-maas", family=ModelFamily.OPEN),
    ModelCandidate(
        model_id="meta/llama-4-maverick-17b-128e-instruct-maas", family=ModelFamily.OPEN
    ),
]

app = typer.Typer(add_completion=False)


@app.command(help="Send one tiny prompt to each candidate model on Vertex AI.")
def main(
    project: Annotated[
        str,
        typer.Option(envvar="GOOGLE_CLOUD_PROJECT", help="GCP project ID to call in."),
    ],
    fallback_location: Annotated[
        str, typer.Option(help="Region to try when a model is not on `global`.")
    ] = "us-central1",
    model: Annotated[
        list[str] | None,
        typer.Option(help="Only check this model ID (repeatable). Default: all."),
    ] = None,
) -> None:
    """Check the candidate models and exit with 1 unless Gemini and Claude both answer.

    Args:
        project: The GCP project ID to call the models in.
        fallback_location: The regional location to try when `global` fails.
        model: Model IDs to check instead of all candidates.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # The client libraries log every call and failure; the summary line is enough here.
    logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    candidates = [
        candidate for candidate in CANDIDATES if not model or candidate.model_id in model
    ]
    logger.info("Checking %d models in project %s", len(candidates), project)
    report = ModelCheckReport.run(
        candidates=candidates, project=project, fallback_location=fallback_location
    )

    if not report.passed:
        logger.error("Need at least one Gemini and one Claude model that answer.")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
