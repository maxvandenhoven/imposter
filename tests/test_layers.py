"""Checks that every package imports only from the layers below it."""

import ast
import sys
from pathlib import Path

import pytest

import imposter

PACKAGE_DIR = Path(imposter.__file__).parent

LAYERS: dict[str, frozenset[str]] = {
    "config": frozenset(),
    "utils": frozenset({"config"}),
    "engine": frozenset({"config", "utils"}),
    "models": frozenset({"config", "utils"}),
    "players": frozenset({"config", "utils", "engine", "models"}),
    "telemetry": frozenset({"config", "utils", "engine", "models"}),
    "judge": frozenset({"config", "utils", "engine", "models", "telemetry"}),
    "words": frozenset({"config", "utils", "models"}),
    "ports": frozenset({"config", "utils", "engine"}),
    "orchestration": frozenset(
        {
            "config",
            "utils",
            "engine",
            "models",
            "players",
            "telemetry",
            "judge",
            "words",
            "ports",
        }
    ),
    "agent": frozenset(
        {
            "config",
            "utils",
            "engine",
            "models",
            "players",
            "telemetry",
            "judge",
            "words",
            "ports",
            "orchestration",
        }
    ),
    "api": frozenset(
        {
            "config",
            "utils",
            "engine",
            "models",
            "players",
            "telemetry",
            "judge",
            "words",
            "ports",
            "orchestration",
            "agent",
        }
    ),
}
"""The parts of the package each part may import from, besides itself."""

PURE_LAYERS = frozenset({"config", "utils", "engine"})
"""The parts that may use only the standard library and pydantic: no ADK, no LLMs."""


def source_files(part: str) -> list[Path]:
    """List the source files of a part of the package, a module or a subpackage."""
    module = PACKAGE_DIR / f"{part}.py"

    return [module] if module.exists() else sorted((PACKAGE_DIR / part).rglob("*.py"))


def imported_modules(path: Path) -> set[str]:
    """List the absolute modules a source file imports."""
    modules: set[str] = set()

    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)

    return modules


@pytest.mark.parametrize("part", list(LAYERS))
def test_parts_import_only_from_lower_layers(part: str) -> None:
    allowed = LAYERS[part] | {part}
    offending = {
        f"{path.name}: {module}"
        for path in source_files(part)
        for module in imported_modules(path)
        if module.startswith("imposter.") and module.split(".")[1] not in allowed
    }

    assert offending == set()


@pytest.mark.parametrize("part", sorted(PURE_LAYERS))
def test_pure_parts_use_only_the_standard_library_and_pydantic(part: str) -> None:
    offending = {
        f"{path.name}: {module}"
        for path in source_files(part)
        for module in imported_modules(path)
        if module.split(".")[0] not in {"imposter", "pydantic", *sys.stdlib_module_names}
    }

    assert offending == set()
