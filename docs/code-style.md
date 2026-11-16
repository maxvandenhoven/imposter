# Code style

This page is the reference for how code and prose in this repository are written, and
for what enforces each rule. The tools catch most slips. The rules marked as review are
the ones to keep in mind while writing, because nothing else catches them.

## Principles

- Keep it simple, and use objects where state or shared logic lives. Behavior that reads
  or changes an object's state is a method on that object, for example
  `game.submit(...)` and `game.view_for(seat)`. Objects change in place, without
  copy-and-reassign updates.
- Use plain functions only for logic on plain values that no object owns, as in
  `utils/text.py`, `utils/tally.py` and `utils/phases.py`.
- Data types carry data and validation only. The pydantic models for configs, events,
  views and responses and the enums have no behavior methods.
- Keep I/O at the edges. The step that calls a model returns data, and a separate step
  applies it to the game.
- Prefer what ADK provides over code of the app's own. A new wrapper around an ADK
  feature needs a reason that the architecture page can state.

## Python

| Rule | Enforced by |
|---|---|
| Lines are at most 90 characters, in code, docstrings and comments. | `ruff format`, ruff `E501` |
| Every function and method has type annotations, including private ones and tests. Test functions return `-> None`. | ruff `ANN`, `ty check` |
| Public classes and functions have Google-style docstrings, which do not repeat types in `Args:` or `Returns:`. | ruff `D` with `convention = "google"` |
| In `src/`, every docstring documents all arguments in `Args:` and the return value in `Returns:`, or `Yields:` for generators, unless the annotation is `None`. | `scripts/tooling/check_docstrings.py` |
| Comments start with a capital letter and end with a period, unless they are shorter than five words. | `scripts/tooling/check_comments.py` |
| The code logs with `logging` and never prints. | ruff `T20` |
| Lines are not split by hand and no trailing comma forces a split. `ruff format` wraps. | `skip-magic-trailing-comma = true` |
| Inline code in docstrings uses single backticks. | review |
| Docstring prose and comments fill the line up to 90 characters. No tool reflows them. | review |
| Exception messages are full sentences that start with a capital letter and end with a period, for example `"Seat 2 has no turn to start in phase vote."`. | review |
| Pytest fixtures state their scope, for example `scope="function"`. | review |
| Distinct blocks of logic are separated by a blank line: before and after every compound statement (`if`, `for`, `while`, `with`, `try`, `match`) unless it starts or ends its block, and before the closing `return` of a function with three or more statements. | review |
| Calls to the app's own functions, methods and classes with two or more arguments pass them by keyword, for example `game.submit(seat=seat, response=response)`. Positional arguments are fine for single-argument calls, the standard library, builtins and third-party APIs. | review |
| FastAPI routes and typer commands set their public text with `description=` and `help=`. | review |

The ruff rule sets are `B`, `D`, `E`, `F`, `I`, `EM`, `T20`, `RET`, `ANN` and `UP`,
configured in `pyproject.toml`. Types are checked with `ty`, not mypy.

## Names

These rules are checked in review.

- Names are specific and consistent across the package. Types, enums and constants
  carry their domain as a prefix, such as `GameEvent`, `PlayerView` and `JudgeVerdict`,
  instead of a bare `Event`, `View` or `Verdict`.
- Related types share a pattern, such as the responses `ClueResponse`,
  `DiscussionResponse` and `VoteResponse`.
- Base classes start with `Base` (`BaseGameEvent`), protocols end with `Protocol`
  (`PlayerProtocol`), and subclasses of ADK types end with their kind: `Agent`, `Node`,
  `Classifier` (`GeminiDecisionsClassifier`) or `Plugin` (`GameTracePlugin`).
- Functions are named after what they return or do, such as `pending_seats` and
  `start_turn`, not `get_` or `do_`.
- Names are public by default. A leading underscore is used only when hiding clearly
  matters, such as state that must change only through methods. Public attributes are
  documented in the `Attributes:` section of the class. This applies to tests too.

## Web app

| Rule | Enforced by |
|---|---|
| TypeScript is strict, with `noUncheckedIndexedAccess`. | `tsc -b --noEmit` |
| The code follows `typescript-eslint` `strictTypeChecked` and the React hooks rules. The shadcn/ui primitives in `frontend/src/components/ui/` and the generated `frontend/src/api/schema.ts` are not linted. | ESLint |
| The print width is 90 and Tailwind classes are sorted. | Prettier |
| `frontend/src/api/schema.ts` is generated with `make api-client` and committed after a change to an API model, an engine event or the `GameRequest`. | review |

[`frontend.md`](frontend.md) has the rules that keep the look of the app consistent.

## Prose

These rules apply to documentation, comments, docstrings, commit messages and the text
of pull requests and issues. They are checked in review.

- Write complete, connected sentences, also in list items and in the explanation cells
  of tables. Avoid fragments such as "Region: `europe-west4`."
- Use no em dashes and no semicolons, and few colons. Split the sentence or use a comma
  instead. Code syntax, such as a semicolon in a shell command, is fine.
- Use US spelling, plain verbs and one name per concept.
- Headings are in sentence case, and the text is in the present tense.
- Documentation describes the system as it is, not how it was built. It does not refer
  to issues, pull requests or plans. A part that does not exist is named as missing or
  planned in the place a reader would look for it.
- A change to behavior updates the page that describes it in the same pull request.

## Git

| Rule | Enforced by |
|---|---|
| Commit messages follow conventional commits, for example `feat(engine): add a phase`. | commitizen, in the `commit-msg` hook |
| `make check` passes before a commit. | the pre-commit hook |
| Branches are named `feature/`, `fix/` or `chore/` plus a short slug. | review |
| `make check test` passes before a push, because there is no CI. | review |
| A pull request says how the change was verified. | review |
| `uv.lock` and `frontend/package-lock.json` are committed. | review |

## Agent hooks

`.claude/settings.json` gives coding agents two hooks. After every edit,
`.claude/hooks/format-file.sh` formats the edited Python file with ruff, runs the
comment checker and, for files in `src/`, the docstring checker, and formats edited
files in `frontend/src/` with Prettier. Errors that remain are reported back to the
agent. When the agent stops, `make check` runs.
