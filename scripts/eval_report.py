"""Summarise and compare the results of `adk eval` runs of the Imposter evals.

`adk eval` writes one result file per run to `evals/<app>/.adk/eval_history/`, which
ADK's `LocalEvalSetResultsManager` reads. This script adds what ADK does not print: the
pass rate of each metric over all cases, the model under test, a breakdown by the kind
of case, and a comparison of two runs that lists the cases whose verdict changed.

Usage:

- `uv run python scripts/eval_report.py show judge_clue` shows the latest run of an app,
  or the run given with `--result`.
- `uv run python scripts/eval_report.py compare player_clue BASE NEW` compares two runs
  by their result ids (the file names without `.evalset_result.json`).
- `uv run python scripts/eval_report.py list player_clue` lists the runs of an app.
- `uv run python scripts/eval_report.py summary [--markdown]` shows the latest run of
  every eval set and model of every app, as tables or as Markdown for the docs.
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from google.adk.evaluation.eval_metrics import EvalStatus
from google.adk.evaluation.eval_result import EvalCaseResult, EvalSetResult
from google.adk.evaluation.local_eval_set_results_manager import (
    LocalEvalSetResultsManager,
)
from rich.console import Console
from rich.table import Table

AGENTS_DIR = "evals"
UNKNOWN_MODEL = "unknown"

console = Console()


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """The pass rate of one metric over the cases of a run.

    Attributes:
        passed: The cases that passed.
        evaluated: The cases with a pass or fail verdict.
    """

    passed: int
    evaluated: int

    @property
    def rate(self) -> float:
        """The share of evaluated cases that passed, 0 when none were evaluated."""
        return self.passed / self.evaluated if self.evaluated else 0.0


def results_manager() -> LocalEvalSetResultsManager:
    """Open ADK's reader of the result files under `evals/`.

    Returns:
        The results manager.
    """
    return LocalEvalSetResultsManager(agents_dir=AGENTS_DIR)


def load_result(*, app: str, result_id: str | None) -> EvalSetResult:
    """Load one run of an app, the latest when no id is given.

    Args:
        app: The eval app, a folder of `evals/`.
        result_id: The id of the run, if not the latest.

    Returns:
        The result of the run.

    Raises:
        typer.BadParameter: When the app has no runs.
    """
    manager = results_manager()
    ids = sorted(
        manager.list_eval_set_results(app), key=lambda run: run.rsplit("_", 1)[-1]
    )

    if not ids:
        message = f"The app {app} has no eval runs in {AGENTS_DIR}/{app}/.adk."
        raise typer.BadParameter(message)

    return manager.get_eval_set_result(
        app_name=app, eval_set_result_id=result_id or ids[-1]
    )


def model_versions(result: EvalSetResult) -> str:
    """List the models that answered in a run, from the events of its sessions.

    Args:
        result: The result of the run.

    Returns:
        The model versions, joined by commas.
    """
    versions = {
        event.model_version
        for case in result.eval_case_results
        if case.session_details
        for event in case.session_details.events
        if event.model_version
    }

    return ", ".join(sorted(versions)) or UNKNOWN_MODEL


def case_statuses(case: EvalCaseResult) -> dict[str, EvalStatus]:
    """Read the verdict of each graded metric of one case.

    Args:
        case: The result of the case.

    Returns:
        The status by metric name, without the informational metrics.
    """
    return {
        metric.metric_name: metric.eval_status
        for metric in case.overall_eval_metric_results
        if metric.eval_status in (EvalStatus.PASSED, EvalStatus.FAILED)
    }


def metric_summaries(cases: list[EvalCaseResult]) -> dict[str, MetricSummary]:
    """Count the passing cases of each metric.

    Args:
        cases: The results of the cases.

    Returns:
        The summary by metric name, in the order the metrics first appear.
    """
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for case in cases:
        for metric, status in case_statuses(case).items():
            counts[metric][0] += status is EvalStatus.PASSED
            counts[metric][1] += 1

    return {
        metric: MetricSummary(passed=passed, evaluated=evaluated)
        for metric, (passed, evaluated) in counts.items()
    }


def case_kind(eval_id: str) -> str:
    """Read the kind of a case from the first part of its id.

    Args:
        eval_id: The id, such as `synonym-gratitude-thanks` or `wallet-4df1-alice-r1`.

    Returns:
        The first part: the label kind for the judge, the secret word for players.
    """
    return eval_id.split("-", 1)[0]


def summary_table(*, title: str, cases: list[EvalCaseResult], by_kind: bool) -> Table:
    """Build the table of pass rates of a run.

    Args:
        title: The title of the table.
        cases: The results of the cases.
        by_kind: Whether to add a row per kind of case.

    Returns:
        The table.
    """
    groups = {"all": cases}

    if by_kind:
        for case in cases:
            groups.setdefault(case_kind(case.eval_id), []).append(case)

    summaries = {group: metric_summaries(members) for group, members in groups.items()}
    metrics = list(summaries["all"])
    table = Table(title=title)
    table.add_column("cases")
    table.add_column("n", justify="right")

    for metric in metrics:
        table.add_column(metric, justify="right")

    for group, members in groups.items():
        cells = [
            f"{summary.passed}/{summary.evaluated} ({summary.rate:.0%})"
            if (summary := summaries[group].get(metric))
            else "-"
            for metric in metrics
        ]
        table.add_row(group, str(len(members)), *cells)

    return table


def app_names() -> list[str]:
    """List the eval apps that have runs.

    Returns:
        The folder names of `evals/` with an eval history, sorted.
    """
    return sorted(
        path.parent.parent.name
        for path in Path(AGENTS_DIR).glob("*/.adk/eval_history")
        if any(path.iterdir())
    )


def latest_runs(*, app: str, since: float) -> list[EvalSetResult]:
    """Load the latest run of each eval set and model of an app.

    Args:
        app: The eval app.
        since: Leave out runs created before this Unix time.

    Returns:
        The runs, sorted by eval set and model.
    """
    manager = results_manager()
    latest: dict[tuple[str, str], EvalSetResult] = {}

    for result_id in manager.list_eval_set_results(app):
        run = manager.get_eval_set_result(app_name=app, eval_set_result_id=result_id)
        key = (run.eval_set_id, model_versions(run))
        current = latest.get(key)

        if run.creation_timestamp >= since and (
            current is None or run.creation_timestamp > current.creation_timestamp
        ):
            latest[key] = run

    return [latest[key] for key in sorted(latest)]


def summary_rows(runs: list[EvalSetResult]) -> tuple[list[str], list[list[str]]]:
    """Build one row of pass rates per run.

    Args:
        runs: The runs.

    Returns:
        The metric names and the rows: eval set, model, cases, then a rate per metric.
    """
    summaries = [metric_summaries(run.eval_case_results) for run in runs]
    metrics = list(dict.fromkeys(name for summary in summaries for name in summary))
    rows = [
        [
            run.eval_set_id,
            model_versions(run),
            str(len(run.eval_case_results)),
            *[
                f"{item.passed}/{item.evaluated} ({item.rate:.0%})"
                if (item := summary.get(metric))
                else "-"
                for metric in metrics
            ],
        ]
        for run, summary in zip(runs, summaries, strict=True)
    ]

    return metrics, rows


app = typer.Typer(add_completion=False, no_args_is_help=True)
AppArgument = Annotated[str, typer.Argument(help="Eval app, a folder of `evals/`.")]


@app.command("list")
def list_runs(app_name: AppArgument) -> None:
    """List the runs of an app, oldest first."""
    for result_id in sorted(
        results_manager().list_eval_set_results(app_name),
        key=lambda run: run.rsplit("_", 1)[-1],
    ):
        console.print(result_id)


@app.command()
def show(
    app_name: AppArgument,
    result: Annotated[
        str | None, typer.Option(help="Run id. Default: the latest.")
    ] = None,
    by_kind: Annotated[bool, typer.Option(help="Add a row per kind of case.")] = False,
) -> None:
    """Show the pass rate of each metric in one run."""
    run = load_result(app=app_name, result_id=result)
    title = f"{run.eval_set_result_id} ({model_versions(run)})"
    console.print(
        summary_table(title=title, cases=run.eval_case_results, by_kind=by_kind)
    )


@app.command()
def compare(app_name: AppArgument, base: str, new: str) -> None:
    """Compare two runs of an app: pass rates and the cases whose verdict changed."""
    runs = [load_result(app=app_name, result_id=run) for run in (base, new)]

    for run in runs:
        title = f"{run.eval_set_result_id} ({model_versions(run)})"
        console.print(
            summary_table(title=title, cases=run.eval_case_results, by_kind=False)
        )

    before = {case.eval_id: case_statuses(case) for case in runs[0].eval_case_results}

    for case in runs[1].eval_case_results:
        for metric, status in case_statuses(case).items():
            earlier = before.get(case.eval_id, {}).get(metric)

            if earlier is not None and earlier is not status:
                console.print(f"{case.eval_id} {metric}: {earlier.name} -> {status.name}")


@app.command()
def summary(
    since: Annotated[
        float, typer.Option(help="Leave out runs created before this Unix time.")
    ] = 0.0,
    markdown: Annotated[
        bool, typer.Option(help="Print Markdown tables, for the docs.")
    ] = False,
) -> None:
    """Show the latest run of every eval set and model, one table per app."""
    for app_name in app_names():
        metrics, rows = summary_rows(latest_runs(app=app_name, since=since))
        header = ["eval set", "model", "cases", *metrics]

        if markdown:
            lines = [
                f"#### {app_name}",
                "",
                "| " + " | ".join(header) + " |",
                "|" + "---|" * len(header),
                *("| " + " | ".join(row) + " |" for row in rows),
                "",
            ]
            console.print("\n".join(lines), markup=False, highlight=False, soft_wrap=True)
            continue

        table = Table(title=app_name)

        for column in header:
            table.add_column(column)

        for row in rows:
            table.add_row(*row)

        console.print(table)


if __name__ == "__main__":
    app()
