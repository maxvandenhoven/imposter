import ast
import sys
from pathlib import Path

import imposter.engine

ENGINE_DIR = Path(imposter.engine.__file__).parent

ALLOWED_THIRD_PARTY = frozenset({"pydantic"})
"""Third-party packages the engine may import."""


def imported_modules(path: Path) -> set[str]:
    """List the absolute modules a source file imports."""
    tree = ast.parse(path.read_text())
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)

    return modules


def test_engine_imports_only_itself_the_standard_library_and_pydantic() -> None:
    offending = {
        f"{path.name}: {module}"
        for path in ENGINE_DIR.glob("*.py")
        for module in imported_modules(path)
        if not module.startswith("imposter.engine")
        and module.split(".")[0] not in sys.stdlib_module_names
        and module.split(".")[0] not in ALLOWED_THIRD_PARTY
    }

    assert offending == set()
