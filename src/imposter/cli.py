"""Command line interface for the `imposter` package."""

import typer

from imposter import __version__

app = typer.Typer(name="imposter", no_args_is_help=True)


@app.callback(help="LLM agents playing the social deduction game Imposter.")
def main() -> None:
    """Group the `imposter` commands."""


@app.command(help="Print the package version.")
def version() -> None:
    """Print the package version."""
    typer.echo(f"imposter {__version__}")
