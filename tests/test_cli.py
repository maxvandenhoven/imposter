from typer.testing import CliRunner

from imposter import __version__
from imposter.cli import app


def test_version_prints_package_version() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output == f"imposter {__version__}\n"


def test_no_arguments_shows_help() -> None:
    result = CliRunner().invoke(app, [])

    assert "version" in result.output
