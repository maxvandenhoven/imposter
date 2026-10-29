from dataclasses import dataclass, field

import pytest
from check_models import (
    CANDIDATES,
    ModelCandidate,
    ModelCheckReport,
    ModelCheckResult,
    ModelFamily,
    app,
)
from typer.testing import CliRunner


@dataclass(frozen=True, slots=True)
class ScriptedCandidate(ModelCandidate):
    """A candidate whose ping fails in the locations listed in `failing_locations`.

    Attributes:
        failing_locations: Locations where the ping raises an error.
        pinged: Locations pinged so far, in order.
    """

    failing_locations: tuple[str, ...] = ()
    pinged: list[str] = field(default_factory=list)

    def ping(self, project: str, location: str) -> str:
        self.pinged.append(location)

        if location in self.failing_locations:
            message = f"404 not found in {location}"
            raise RuntimeError(message)

        return "OK"


def scripted(
    family: ModelFamily = ModelFamily.GEMINI, failing_locations: tuple[str, ...] = ()
) -> ScriptedCandidate:
    return ScriptedCandidate(
        model_id="model", family=family, failing_locations=failing_locations
    )


class TestModelCandidateCheck:
    def test_global_success_does_not_try_fallback(self) -> None:
        candidate = scripted()

        result = candidate.check(project="p", fallback_location="us-central1")

        assert result.ok
        assert result.location == "global"
        assert candidate.pinged == ["global"]

    def test_falls_back_to_regional_location(self) -> None:
        candidate = scripted(failing_locations=("global",))

        result = candidate.check(project="p", fallback_location="us-central1")

        assert result.ok
        assert result.location == "us-central1"
        assert candidate.pinged == ["global", "us-central1"]

    def test_failure_everywhere_reports_global_and_fallback_errors(self) -> None:
        candidate = scripted(failing_locations=("global", "us-central1"))

        result = candidate.check(project="p", fallback_location="us-central1")

        assert not result.ok
        assert "global: RuntimeError: 404 not found in global" in result.detail
        assert "us-central1: RuntimeError: 404 not found in us-central1" in result.detail


class TestModelCheckReport:
    @pytest.mark.parametrize(
        ("ok_families", "expected"),
        [
            ((ModelFamily.GEMINI, ModelFamily.CLAUDE), True),
            ((ModelFamily.GEMINI, ModelFamily.CLAUDE, ModelFamily.OPEN), True),
            ((ModelFamily.GEMINI,), False),
            ((ModelFamily.CLAUDE, ModelFamily.OPEN), False),
        ],
    )
    def test_passes_with_one_gemini_and_one_claude_model(
        self, ok_families: tuple[ModelFamily, ...], expected: bool
    ) -> None:
        results = [
            ModelCheckResult(
                candidate=scripted(family=family),
                ok=family in ok_families,
                location="global",
                detail="",
            )
            for family in ModelFamily
        ]

        assert ModelCheckReport(results=results).passed is expected


def test_candidates_cover_every_family() -> None:
    assert {candidate.family for candidate in CANDIDATES} == set(ModelFamily)


def test_cli_requires_a_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    result = CliRunner().invoke(app, [])

    assert result.exit_code != 0
