import pytest
from conftest import FakeGameSetup
from typer.testing import CliRunner

from imposter import __version__
from imposter.cli import app
from imposter.orchestration.setup import GameSetup


@pytest.fixture(scope="function")
def fake_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `imposter play` seat random players instead of real models."""

    def load(cls: type[GameSetup], seed: int | None = None) -> GameSetup:
        return FakeGameSetup()

    monkeypatch.setattr(GameSetup, "load", classmethod(load))


def test_version_prints_package_version() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output == f"imposter {__version__}\n"


def test_no_arguments_shows_help() -> None:
    result = CliRunner().invoke(app, [])

    assert "version" in result.output
    assert "play" in result.output


@pytest.mark.usefixtures("fake_setup")
def test_play_prints_the_game_with_outcome_debrief_and_cost() -> None:
    result = CliRunner().invoke(app, ["play", "--word", "giraffe", "--seed", "3"])

    assert result.exit_code == 0, result.output
    assert "the word was giraffe" in result.output
    assert "Debrief" in result.output
    assert "Tokens and cost" in result.output
    assert "imposter" not in result.output.split("Outcome")[0].lower()


@pytest.mark.usefixtures("fake_setup")
def test_play_in_god_mode_shows_the_secrets_up_front() -> None:
    result = CliRunner().invoke(
        app,
        ["play", "--word", "giraffe", "--god", "-p", "gemini-flash-lite"]
        + ["-p", "gpt-oss"] * 2,
    )

    assert result.exit_code == 0, result.output
    assert "Word: giraffe" in result.output.split("Clue round 1")[0]


@pytest.mark.usefixtures("fake_setup")
def test_play_rejects_unknown_models() -> None:
    result = CliRunner().invoke(app, ["play", "-p", "nope", "-p", "nope", "-p", "nope"])

    assert result.exit_code == 2
