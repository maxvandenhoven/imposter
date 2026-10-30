"""Command line interface for the `imposter` package."""

import asyncio
import os
import uuid
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from imposter import __version__
from imposter.config import GameConfig, IdentityMode
from imposter.engine.events import (
    BaseGameEvent,
    ClueGivenEvent,
    GameAbortedEvent,
    GameStartedEvent,
    GuessMadeEvent,
    OutcomeEvent,
    PhaseStartedEvent,
    PlayerErrorEvent,
    ReflectionEvent,
    SecretWordSaidEvent,
    StatementMadeEvent,
    UsageEvent,
    VoteCastEvent,
    VotesRevealedEvent,
)
from imposter.engine.game import Game
from imposter.models.catalog import ModelCatalog
from imposter.orchestration.adk_runner import run_game
from imposter.orchestration.setup import DEFAULT_MODEL_IDS, GameRequest, GameSetup
from imposter.ports.event_bus import InMemoryEventBus
from imposter.ports.game_store import InMemoryGameStore
from imposter.telemetry.cost import estimated_cost
from imposter.telemetry.setup import TelemetryExporter, setup_telemetry, trace_url
from imposter.telemetry.spans import GameTracePlugin
from imposter.words.options import WordMode, WordOptions

app = typer.Typer(name="imposter", no_args_is_help=True)


class GameEventPrinter:
    """Prints the events of a game in the terminal as they arrive.

    In audience mode secrets stay hidden until the outcome reveals them. In god mode the
    word, the roles, the votes as they are cast and every private reasoning are shown.

    Attributes:
        console: Where the game is printed.
        catalog: The models, for the cost estimate.
        god: Whether to show the secrets and the private reasoning.
        names: The display name of each seat, known from the `game_started` event.
        usages: The usage events so far, for the totals.
    """

    def __init__(self, *, console: Console, catalog: ModelCatalog, god: bool) -> None:
        """Initialize the printer.

        Args:
            console: Where the game is printed.
            catalog: The models, for the cost estimate.
            god: Whether to show the secrets and the private reasoning.
        """
        self.console = console
        self.catalog = catalog
        self.god = god
        self.names: dict[int, str] = {}
        self.usages: list[UsageEvent] = []

    def print_event(self, event: BaseGameEvent) -> None:
        """Print one event.

        Args:
            event: The event.
        """
        match event:
            case GameStartedEvent():
                self.print_start(event)
            case PhaseStartedEvent(phase=phase, round=round_):
                title = f"{phase} round {round_}" if round_ else str(phase)
                self.console.rule(title.capitalize())
            case ClueGivenEvent(seat=seat, clue=clue):
                said = f"[bold]{escape(clue)}[/bold]" if clue else "[dim]passes[/dim]"
                self.console.print(f"{self.name(seat)}: {said}")
                self.print_reasoning(event.private_reasoning)
            case StatementMadeEvent(seat=seat, statement=statement):
                self.console.print(f"{self.name(seat)}: {escape(statement)}")
                self.print_reasoning(event.private_reasoning)
            case VoteCastEvent(seat=seat, target=target):
                voted = f"votes for {self.name(target)}" if self.god else "has voted"
                self.console.print(f"{self.name(seat)} {voted}")
                self.print_reasoning(event.private_reasoning)
            case VotesRevealedEvent():
                self.print_votes(event)
            case GuessMadeEvent(seat=seat, guess=guess, correct=correct):
                verdict = "[green]correct[/green]" if correct else "[red]wrong[/red]"
                self.console.print(
                    f"{self.name(seat)} guesses [bold]{escape(guess or '-')}[/bold]: "
                    f"{verdict} ({event.judged_by})"
                )
                self.print_reasoning(event.private_reasoning)
            case SecretWordSaidEvent(seat=seat):
                self.console.print(f"[red]{self.name(seat)} said the secret word![/red]")
            case OutcomeEvent():
                self.print_outcome(event)
            case ReflectionEvent(seat=seat, reflection=reflection):
                self.console.print(
                    f"[bold]{self.name(seat)}[/bold]: {escape(reflection)}"
                )
            case PlayerErrorEvent(seat=seat, message=message):
                self.console.print(
                    f"[yellow]{self.name(seat)}: {escape(message)}[/yellow]"
                )
            case UsageEvent():
                self.usages.append(event)
            case GameAbortedEvent(reason=reason):
                self.console.print(f"[red]Game aborted: {escape(reason)}[/red]")

    def name(self, seat: int | None) -> str:
        """Get the display name of a seat.

        Args:
            seat: The seat, `None` for an abstention.

        Returns:
            The name, or `nobody`.
        """
        return "nobody" if seat is None else escape(self.names.get(seat, f"Seat {seat}"))

    def print_start(self, event: GameStartedEvent) -> None:
        """Print the players and, in god mode, the secrets.

        Args:
            event: The `game_started` event.
        """
        self.names = {seat.seat: seat.name for seat in event.seats}
        table = Table("Seat", "Player", *(("Model", "Role") if self.god else ()))

        for seat in event.seats:
            secrets = ()

            if self.god:
                role = "imposter" if seat.seat in event.imposters else "civilian"
                secrets = (event.seat_models[seat.seat], role)

            table.add_row(str(seat.seat), escape(seat.name), *secrets)

        self.console.print(table)

        if event.public_category:
            self.console.print(f"Category: {escape(event.public_category)}")

        if self.god:
            self.console.print(
                f"[magenta]Word: {escape(event.word)}, category: "
                f"{escape(event.category or '-')}, hint: {escape(event.hint or '-')}"
                "[/magenta]"
            )

    def print_reasoning(self, reasoning: str) -> None:
        """Print private reasoning, in god mode only.

        Args:
            reasoning: The private reasoning of a turn.
        """
        if self.god and reasoning:
            self.console.print(f"  [dim italic]{escape(reasoning)}[/dim italic]")

    def print_votes(self, event: VotesRevealedEvent) -> None:
        """Print every vote and who was caught.

        Args:
            event: The `votes_revealed` event.
        """
        for vote in event.votes:
            self.console.print(
                f"{self.name(vote.voter)} voted for {self.name(vote.target)}"
            )

        caught = ", ".join(self.name(seat) for seat in event.caught) or "nobody"
        self.console.print(f"Caught: [bold]{caught}[/bold]")

    def print_outcome(self, event: OutcomeEvent) -> None:
        """Print how the game ended and reveal the secrets.

        Args:
            event: The `outcome` event.
        """
        imposters = ", ".join(self.name(seat) for seat in event.imposters)
        who = "the imposters were" if len(event.imposters) > 1 else "the imposter was"
        outcome = event.outcome.replace("_", " ").capitalize()
        self.console.print(
            f"[bold green]{outcome}[/bold green]: the word was "
            f"[bold]{escape(event.word)}[/bold], {who} {imposters}"
        )

    def print_totals(self) -> None:
        """Print the tokens and the estimated cost per model."""
        table = Table("Model", "Input", "Output", "Thinking", "Cost (USD)")
        total_cost = 0.0

        for model_id in sorted({usage.model_id for usage in self.usages}):
            usages = [usage for usage in self.usages if usage.model_id == model_id]
            input_tokens = sum(usage.input_tokens for usage in usages)
            output_tokens = sum(usage.output_tokens for usage in usages)
            thinking_tokens = sum(usage.thinking_tokens for usage in usages)
            cost = estimated_cost(
                price=self.catalog.entry(model_id).price_per_mtok,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
            )
            total_cost += cost
            table.add_row(
                model_id,
                str(input_tokens),
                str(output_tokens),
                str(thinking_tokens),
                f"{cost:.4f}",
            )

        table.add_row("total", "", "", "", f"{total_cost:.4f}")
        self.console.rule("Tokens and cost")
        self.console.print(table)


async def play_game(
    *,
    request: GameRequest,
    setup: GameSetup,
    printer: GameEventPrinter,
    project: str | None = None,
) -> Game:
    """Play a game, print its events as they arrive on the bus and link its trace.

    Args:
        request: The options and how to choose the word.
        setup: Creates the game and seats its players.
        printer: Prints the events.
        project: The Google Cloud project the trace goes to, if it is exported there.

    Returns:
        The game, done or aborted.
    """
    bus = InMemoryEventBus()
    store = InMemoryGameStore()
    plugin = GameTracePlugin(find_game=store.get)
    game_id = uuid.uuid4().hex

    async def print_events() -> None:
        async for event in bus.subscribe(game_id=game_id):
            printer.print_event(event)

    game, _ = await asyncio.gather(
        run_game(
            request=request,
            setup=setup,
            bus=bus,
            store=store,
            game_id=game_id,
            trace_plugin=plugin,
        ),
        print_events(),
    )
    printer.print_totals()

    if project and game_id in plugin.trace_ids:
        url = trace_url(project=project, trace_id=plugin.trace_ids[game_id])
        printer.console.print(f"Trace: {url}", soft_wrap=True)

    return game


@app.callback(help="LLM agents playing the social deduction game Imposter.")
def main() -> None:
    """Group the `imposter` commands."""


@app.command(help="Print the package version.")
def version() -> None:
    """Print the package version."""
    typer.echo(f"imposter {__version__}")


@app.command(help="Play a game between models in the terminal.")
def play(
    players: Annotated[
        list[str] | None,
        typer.Option(
            "--player", "-p", help="The catalog id of a seat's model, once per seat."
        ),
    ] = None,
    word: Annotated[
        str | None, typer.Option(help="The secret word, which sets the word mode typed.")
    ] = None,
    word_mode: Annotated[
        WordMode | None, typer.Option(help="How the word is chosen, random by default.")
    ] = None,
    category: Annotated[
        str | None, typer.Option(help="The category of a random or typed word.")
    ] = None,
    imposters: Annotated[int, typer.Option(help="The number of imposters.")] = 1,
    identity_mode: Annotated[
        IdentityMode, typer.Option(help="How players are named.")
    ] = IdentityMode.NAMES,
    clue_rounds: Annotated[int, typer.Option(help="The number of clue rounds.")] = 2,
    discussion_rounds: Annotated[
        int, typer.Option(help="The number of discussion rounds.")
    ] = 2,
    public_category: Annotated[
        bool, typer.Option(help="Tell every player the category.")
    ] = False,
    imposter_hint: Annotated[
        bool, typer.Option(help="Give imposters a related hint word.")
    ] = False,
    model_clue_check: Annotated[
        bool, typer.Option(help="Let a model judge clues that pass the code checks.")
    ] = True,
    token_budget: Annotated[
        int, typer.Option(help="The tokens the game may use before it is aborted.")
    ] = 200_000,
    seed: Annotated[
        int | None, typer.Option(help="A seed for seat order, roles and random words.")
    ] = None,
    god: Annotated[
        bool, typer.Option(help="Show the secrets and the private reasoning.")
    ] = False,
    telemetry: Annotated[
        TelemetryExporter | None,
        typer.Option(
            envvar="IMPOSTER_TELEMETRY",
            help="Where traces go: cloud by default when GOOGLE_CLOUD_PROJECT is set, "
            "otherwise none.",
        ),
    ] = None,
) -> None:
    """Play a game between models and print it as it happens.

    Args:
        players: The catalog ids of the models, one per seat.
        word: The secret word, if typed.
        word_mode: How the word is chosen.
        category: The category of a random or typed word.
        imposters: The number of imposters.
        identity_mode: How players are named.
        clue_rounds: The number of clue rounds.
        discussion_rounds: The number of discussion rounds.
        public_category: Whether every player learns the category.
        imposter_hint: Whether imposters get a hint word.
        model_clue_check: Whether a model judges clues that pass the code checks.
        token_budget: The tokens the game may use before it is aborted.
        seed: An optional seed for reproducible games.
        god: Whether to show the secrets and the private reasoning.
        telemetry: Where traces go, chosen from the environment when not given.

    Raises:
        BadParameter: When the options do not make a valid game.
    """
    setup = GameSetup.load(seed=seed)
    mode = word_mode or (WordMode.TYPED if word else WordMode.RANDOM)

    try:
        config = GameConfig(
            players=setup.player_configs(players or DEFAULT_MODEL_IDS),
            imposter_count=imposters,
            identity_mode=identity_mode,
            public_category=public_category,
            imposter_hint=imposter_hint,
            model_clue_check=model_clue_check,
            clue_rounds=clue_rounds,
            discussion_rounds=discussion_rounds,
            token_budget=token_budget,
            seed=seed,
        )
        request = GameRequest(
            config=config, words=WordOptions(mode=mode, word=word, category=category)
        )
    except (KeyError, ValidationError) as error:
        raise typer.BadParameter(str(error)) from error

    if telemetry is None:
        cloud = bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
        telemetry = TelemetryExporter.CLOUD if cloud else TelemetryExporter.NONE

    project = setup_telemetry(exporter=telemetry)
    printer = GameEventPrinter(console=Console(), catalog=setup.catalog, god=god)
    asyncio.run(play_game(request=request, setup=setup, printer=printer, project=project))
