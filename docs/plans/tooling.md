# Tooling

Tooling mirrors the hive repo (`maxvandenhoven/hive`, locally `~/Documents/repos/hive`).
WP 01 copies the setup and adapts names; when in doubt, hive's `pyproject.toml`,
`Makefile`, `.pre-commit-config.yaml`, `CLAUDE.md`, `.claude/` and `scripts/tooling/` are
the reference.

## Python

- Python `~=3.13.0`, `uv` with `uv_build` backend, `uv.lock` committed.
- Package `imposter` in `src/imposter/`, entry point `imposter = "imposter.cli:app"`
  (Typer).
- Dev group: `pytest`, `pytest-cov`, `pytest-asyncio`, `hypothesis`, `httpx`, `ruff`,
  `ty`, `pre-commit`.

## Style rules

Same rules as hive (see its `docs/plans/tooling.md` and `CLAUDE.md`), summarised:

| Rule | Enforced by |
|---|---|
| Line length 90 for code, docstrings and comments | `ruff format`, ruff `E501` |
| Type annotations everywhere, including tests | ruff `ANN`, `ty check` |
| Google-style docstrings; do not repeat types in `Args:`/`Returns:` | ruff `D`, `convention = "google"` |
| Docstrings in `src/` document all args and the return value | `scripts/tooling/check_docstrings.py` |
| Comments start with a capital letter and end with a period at 5+ words | `scripts/tooling/check_comments.py` |
| Single backticks for inline code in docstrings | review |
| No `print`, use `logging` | ruff `T20` |
| No manual line splitting or magic trailing commas | `skip-magic-trailing-comma = true` |
| Pytest fixtures state their scope explicitly | review |
| Behaviour is a method on the type that owns the data | review |
| Specific, domain-prefixed names (`GameEvent`, `PlayerView`, `JudgeVerdict`) | review |
| Public by default; underscore only when hiding matters | review |
| Blank lines around compound statements and before a multi-step `return` | review |
| Keyword arguments for own calls with 2+ arguments | review |

Ruff rules: `B`, `D`, `E`, `F`, `I`, `EM`, `T20`, `RET`, `ANN`, `UP`, with the same ignores
and per-file test ignores as hive.

## Makefile

```
make sync           # uv sync --all-groups
make format         # ruff format + import sorting
make lint           # ruff check --fix, comment and docstring checkers
make type           # ty check
make check          # format + lint + type
make test           # pytest, excluding `slow`, with coverage
make test-slow      # pytest -m slow (real Vertex AI calls)
make css            # standalone Tailwind CLI build (downloads the pinned binary to .bin/)
make dev            # css + uvicorn with reload
make adk-web        # adk web src/imposter
make play ARGS=...  # imposter play
make build          # Cloud Build image
make deploy         # build + terraform apply with the image digest
make tf-state-bucket # create the Terraform state bucket once (gcloud)
make tf-init        # terraform init for infra with the state bucket
make tf-plan        # terraform plan for infra
make tf-apply       # terraform apply for infra
make install-hooks  # pre-commit hooks (including commit-msg)
```

Terraform is formatted and validated by `make check` (`terraform fmt -check -recursive
infra` and `terraform validate` per root) when Terraform is installed.

## Pre-commit and git

- `.pre-commit-config.yaml`: `end-of-file-fixer`, commitizen (`commit-msg`), `make check`.
- Conventional commits, branches `feature/`, `fix/`, `chore/`.
- No CI/CD (README D18); `make check test` before pushing.

## Claude Code

- `CLAUDE.md`: project context pointer (`docs/plans/README.md`), structure, commands, the
  style rules above, git workflow.
- `.claude/settings.json`: PostToolUse on `Edit|Write|MultiEdit` runs
  `.claude/hooks/format-file.sh` (ruff format, ruff check --fix, comment checker on edited
  `.py` files); Stop runs `make check`.
