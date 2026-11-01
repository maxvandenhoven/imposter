"""Time one realistic player turn per catalog model on Vertex AI.

Plays a game with random players up to a clue turn and up to the imposter's guess, renders
the real prompts of those turns and sends them to each catalog model with the model object
and generation settings the players use (`models/factory.py`). Prints per model and phase
the time to the first streamed chunk, the total time, the output tokens and the thinking
tokens of each run, with the median and the slowest total time.

Usage: `uv run --env-file .env python scripts/measure_models.py [--model ID ...]
[--runs N]`. Credentials come from ADC and the project from `GOOGLE_CLOUD_PROJECT`.
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass
from typing import Annotated

import typer
from google.adk.models import BaseLlm, LlmRequest
from google.genai import types

from imposter.config import GameConfig, GamePhase, SecretWord
from imposter.engine.game import Game
from imposter.models.catalog import ModelCatalog, ModelCatalogEntry
from imposter.models.factory import adk_model, generate_content_config
from imposter.orchestration.runner import GameRunner
from imposter.players.fake import RandomPlayer
from imposter.players.prompt import PlayerPromptRenderer

logger = logging.getLogger("measure_models")
MEASURED_PHASES = (GamePhase.CLUE, GamePhase.GUESS)
PLAYER_COUNT = 4


@dataclass(frozen=True, slots=True)
class TurnMeasurement:
    """The timing of one streamed model call.

    Attributes:
        first_chunk_seconds: The time to the first streamed chunk.
        total_seconds: The time to the last chunk.
        output_tokens: The answer tokens, including thinking.
        thinking_tokens: The tokens spent on thinking.
    """

    first_chunk_seconds: float
    total_seconds: float
    output_tokens: int
    thinking_tokens: int


async def prompts_by_phase() -> dict[GamePhase, tuple[str, str]]:
    """Play random players up to a clue turn and the imposter's guess and render both.

    Returns:
        The system instruction and the user message of each measured phase.
    """
    config = GameConfig.model_validate(
        {
            "players": [
                {"model_id": f"m{seat}", "model_display_name": f"Model {seat}"}
                for seat in range(PLAYER_COUNT)
            ],
            "seed": 3,
            "model_clue_check": False,
        }
    )
    game = Game.create(config=config, secret=SecretWord(word="lighthouse"))
    runner = GameRunner(players=[RandomPlayer(seed=seat) for seat in range(PLAYER_COUNT)])
    renderer = PlayerPromptRenderer()
    prompts = {}
    # The second seat has clues from the first one in its view.
    prompts[GamePhase.CLUE] = render(renderer=renderer, game=game, seat=1)

    while game.phase is not GamePhase.GUESS:
        await runner.play_step(game)

    game.start_turn(game.imposters[0])
    prompts[GamePhase.GUESS] = render(
        renderer=renderer, game=game, seat=game.imposters[0]
    )

    return prompts


def render(*, renderer: PlayerPromptRenderer, game: Game, seat: int) -> tuple[str, str]:
    """Render the system instruction and the user message of a seat's turn.

    Args:
        renderer: The prompt renderer.
        game: The game, with the seat's turn started where needed.
        seat: The seat.

    Returns:
        The system instruction and the instruction with the task as one message.
    """
    view = game.view_for(seat)
    task = renderer.task(view=view, include_schema=True)

    return renderer.system(), f"{renderer.instruction(view)}\n\n{task}"


async def measure(
    *, model: BaseLlm, entry: ModelCatalogEntry, phase: GamePhase, prompt: tuple[str, str]
) -> TurnMeasurement:
    """Send one prompt and time the streamed answer.

    Args:
        model: The ADK model object of the entry.
        entry: The catalog entry.
        phase: The phase of the prompt, which sets the output limit.
        prompt: The system instruction and the user message.

    Returns:
        The timings and token counts.
    """
    system, message = prompt
    config = generate_content_config(entry=entry, phase=phase)
    config.system_instruction = system
    request = LlmRequest(
        model=entry.adk_model,
        contents=[types.Content(role="user", parts=[types.Part(text=message)])],
        config=config,
    )
    start = time.perf_counter()
    first = None
    usage = None

    async for response in model.generate_content_async(request, stream=True):
        first = first if first is not None else time.perf_counter() - start
        usage = response.usage_metadata or usage

    return TurnMeasurement(
        first_chunk_seconds=first or 0.0,
        total_seconds=time.perf_counter() - start,
        output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        thinking_tokens=(usage.thoughts_token_count or 0) if usage else 0,
    )


async def run(*, model_ids: list[str] | None, runs: int) -> None:
    """Measure the catalog models, logging each run and a summary per model and phase.

    Args:
        model_ids: The catalog ids to measure, all when empty.
        runs: The runs per model and phase.
    """
    prompts = await prompts_by_phase()
    catalog = ModelCatalog.load()
    entries = [
        entry for entry in catalog.entries if not model_ids or entry.id in model_ids
    ]

    for entry in entries:
        model = adk_model(entry)

        for phase in MEASURED_PHASES:
            totals = []

            for _ in range(runs):
                try:
                    result = await measure(
                        model=model, entry=entry, phase=phase, prompt=prompts[phase]
                    )
                except Exception as error:
                    logger.info("%-18s %-6s FAIL %s", entry.id, phase, str(error)[:120])
                    continue

                totals.append(result.total_seconds)
                logger.info(
                    "%-18s %-6s first %5.1fs total %5.1fs out %4d thinking %4d",
                    entry.id,
                    phase,
                    result.first_chunk_seconds,
                    result.total_seconds,
                    result.output_tokens,
                    result.thinking_tokens,
                )

            if totals:
                logger.info(
                    "%-18s %-6s median %.1fs max %.1fs",
                    entry.id,
                    phase,
                    statistics.median(totals),
                    max(totals),
                )


app = typer.Typer(add_completion=False)


@app.command(help="Time one realistic clue and guess turn per catalog model.")
def main(
    model: Annotated[
        list[str] | None, typer.Option(help="Only this catalog id (repeatable).")
    ] = None,
    runs: Annotated[int, typer.Option(help="Runs per model and phase.")] = 5,
) -> None:
    """Measure the models.

    Args:
        model: Catalog ids to measure instead of all.
        runs: The runs per model and phase.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
    asyncio.run(run(model_ids=model, runs=runs))


if __name__ == "__main__":
    app()
