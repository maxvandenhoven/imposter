"""Build the ADK eval sets of `evals/` from exported games and hand-made labels.

The input is what `scripts/harvest_traces.py` exported to `evals/raw/<day>/logs.jsonl`:
one Cloud Logging entry per model call with its prompt and answer. Three commands:

- `labels` collects every clue that was proposed for a secret word, by players or to the
  judge, and adds the new ones to `evals/data/clue_labels.yaml` without a label. A person
  then labels them by hand. Existing labels are kept.
- `judge` turns the labelled clues into the eval set of the clue judge
  (`evals/judge_clue/`). Clues that the code checks decide never reach the judge model,
  so they are left out (`tests/evals/test_clue_labels.py` checks them instead).
- `players` turns the first attempt of every logged clue, discussion and debrief turn
  into a case of the player evals (`evals/player_clue/`, `evals/player_discussion/`,
  `evals/player_debrief/`), split by secret word into a development and a holdout eval
  set. The turns whose logged answer said the secret word also form a `word_said` eval
  set of hard cases, each repeated, because saying the word is rare per call.

Eval sets store the inputs as data in the session state: the `PlayerView` for players,
from which the eval agents render the prompts with the production templates, so a
prompt change needs no rebuild. A view is parsed back from the logged prompt and kept
only when rendering it again gives exactly the logged prompt.

Usage: `uv run python scripts/build_evalsets.py {labels,judge,players}`.
"""

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from google.adk.evaluation.eval_case import EvalCase, Invocation, SessionInput
from google.adk.evaluation.eval_rubrics import Rubric, RubricContent
from google.adk.evaluation.eval_set import EvalSet
from google.genai import types
from pydantic import BaseModel, ConfigDict

from imposter.config import GamePhase, PlayerRole
from imposter.engine.events import PublicSeat, PublicVote
from imposter.engine.views import (
    GameReveal,
    GameRules,
    PlayerView,
    PublicClue,
    PublicGuess,
    PublicStatement,
    ScratchpadEntry,
    VoteResult,
)
from imposter.judge.checks import clue_check
from imposter.judge.llm_judge import VALID_CLUE_TASK
from imposter.players.prompt import OUTCOME_TEXTS, PlayerPromptRenderer
from imposter.utils.text import mentions_word, normalize_word

RAW_DIR = Path("evals/raw")
LABELS_PATH = Path("evals/data/clue_labels.yaml")
JUDGE_DIR = Path("evals/judge_clue")
PLAYER_DIRS = {
    GamePhase.CLUE: Path("evals/player_clue"),
    GamePhase.DISCUSSION: Path("evals/player_discussion"),
    GamePhase.DEBRIEF: Path("evals/player_debrief"),
}
"""The eval app of each phase whose turns are evaluated."""

TURN_PATTERNS = {
    GamePhase.CLUE: r"It is clue round (\d+) of \d+ and your turn",
    GamePhase.DISCUSSION: r"It is discussion round (\d+) of \d+ and your turn",
    GamePhase.DEBRIEF: r"The game is over and everything is revealed",
}
"""How the task of each evaluated phase starts, with the round as the group if any."""

LOG_FILE_NAME = "logs.jsonl"
INSTRUCTION_START = "<<<BEGIN_SYSTEM_INSTRUCTION>>>"
INSTRUCTION_END = "<<<END_SYSTEM_INSTRUCTION>>>"
EVAL_USER = "eval"

HOLDOUT_SHARE = 0.3
"""The part of the secret words whose turns go to the holdout eval set."""

WORD_SAID_REPEATS = 5
"""How often each hard case of a `word_said` eval set is repeated."""

QUALITY_RUBRIC_TYPE = "FINAL_RESPONSE_QUALITY"
"""The rubric type that ADK's `rubric_based_final_response_quality_v1` grades."""

PLAYER_VIEW_RUBRIC_TYPE = "PLAYER_VIEW"
"""A rubric type no built-in metric grades: it hands the view to the custom metrics."""

SECRET_WORD_RUBRIC_TYPE = "SECRET_WORD"
"""A rubric type no built-in metric grades: it hands the secret word to the metrics,
also for imposters, whose view does not hold it."""

QUALITY_RUBRICS = {
    "civilian": (
        'The clue in the response is not a synonym or near-synonym of "{word}": it does '
        'not mean the same thing and could not stand in for "{word}" in a sentence. '
        "Related ideas such as parts, places, uses, causes, effects and examples are "
        "fine."
    ),
    "imposter": (
        'The secret word, unknown to this player, is "{word}". Next to the clues given '
        "before it in the prompt, the clue in the response fits the secret word about "
        "as well as a clue of a player who knows the word, so it does not stand out as "
        "vague, generic or unrelated."
    ),
    "statement": (
        "Every claim that the statement in the response makes about the game, such as "
        "who gave which clue or said what, matches the game so far in the prompt."
    ),
    "reflection": (
        "The reflection in the response names concrete clues, statements or votes of "
        "this game, and every claim it makes about the game matches the game so far "
        "and the reveal in the prompt."
    ),
}
"""The quality rubric of each player eval set, graded by the built-in rubric metric."""

LABELS_HEADER = """\
# Hand-made labels of clues proposed in played games, collected from the logs by
# `scripts/build_evalsets.py labels`. Label every new entry (null) by hand:
#
# - legal: whether the clue is allowed. Only forms of the secret word are illegal: the
#   word itself, other grammatical forms, a word that contains it or is contained in
#   it, a word with the same stem, and translations. Synonyms are legal.
# - synonym: whether the clue means the same as the secret word, so that it could stand
#   in for it in a sentence. Legal, but a weak clue that gives the word away.
# - note: optional, why a label is not obvious.
"""

logger = logging.getLogger("build_evalsets")


class ClueLabel(BaseModel):
    """A hand-made label of one clue for one secret word.

    Attributes:
        word: The secret word, lowercase.
        clue: The clue, lowercase.
        legal: Whether the clue is allowed, `None` until labelled.
        synonym: Whether the clue is a synonym of the word, `None` until labelled.
        note: Why a label is not obvious, if needed.
    """

    model_config = ConfigDict(frozen=True)

    word: str
    clue: str
    legal: bool | None = None
    synonym: bool | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class LoggedCall:
    """One model call as ADK logged it.

    Attributes:
        trace_id: The trace of the game.
        agent: The ADK agent name, such as `player_2_clue` or `judge`.
        inputs: The text of each input message.
        output: The answer text, its streamed chunks joined.
    """

    trace_id: str
    agent: str
    inputs: list[str]
    output: str

    @property
    def instruction(self) -> str | None:
        """The rendered player instruction, without ADK's markers, if there is one."""
        first = self.inputs[0] if self.inputs else ""

        if INSTRUCTION_START not in first:
            return None

        return first.rsplit(INSTRUCTION_START, 1)[1].rsplit(INSTRUCTION_END, 1)[0].strip()

    @property
    def task(self) -> str:
        """The task message, the last input message."""
        return self.inputs[-1].strip() if self.inputs else ""


def message_texts(raw: str) -> list[str]:
    """Join the text parts of each logged message.

    Args:
        raw: The JSON of a `gen_ai.input.messages` or `gen_ai.output.messages` label.

    Returns:
        The text of each message.
    """
    return [
        "".join(str(part.get("content", "")) for part in message.get("parts", []))
        for message in json.loads(raw or "[]")
    ]


def logged_calls(raw_dir: Path) -> list[LoggedCall]:
    """Read the model calls of every export, each log entry once.

    Args:
        raw_dir: The folder with one export folder per day.

    Returns:
        The calls, in the order of the exports.
    """
    calls = []
    seen = set()

    for path in sorted(raw_dir.glob(f"*/{LOG_FILE_NAME}")):
        for line in path.read_text().splitlines():
            entry = json.loads(line)

            if entry["insertId"] in seen:
                continue

            seen.add(entry["insertId"])
            labels = entry.get("labels", {})
            calls.append(
                LoggedCall(
                    trace_id=entry.get("trace", ""),
                    agent=labels.get("gen_ai.agent.name", ""),
                    inputs=message_texts(labels.get("gen_ai.input.messages", "")),
                    output="".join(
                        message_texts(labels.get("gen_ai.output.messages", ""))
                    ),
                )
            )

    return calls


def player_phase(call: LoggedCall) -> GamePhase | None:
    """Find the phase of a player call from its agent name, `player_{seat}_{phase}`.

    Args:
        call: The call.

    Returns:
        The phase, or `None` for other agents such as the judge.
    """
    match = re.fullmatch(r"player_\d+_(\w+)", call.agent)

    return GamePhase(match.group(1)) if match else None


def secret_words(calls: Iterable[LoggedCall]) -> dict[str, str]:
    """Find the secret word of each game in the prompts of its civilians.

    Args:
        calls: The calls.

    Returns:
        The secret word by trace id.
    """
    words = {}

    for call in calls:
        match = re.search(r'The secret word (?:is|was) "([^"]+)"', call.instruction or "")

        if match:
            words[call.trace_id] = match.group(1)

    return words


def answer_field(*, output: str, field: str) -> str | None:
    """Read one string field from a JSON answer, also when text surrounds the JSON.

    Args:
        output: The answer text.
        field: The field name, such as `clue`.

    Returns:
        The value of the last occurrence of the field, or `None`.
    """
    values = re.findall(rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"', output)

    return json.loads(f'"{values[-1]}"') if values else None


def clue_pairs(calls: list[LoggedCall]) -> set[tuple[str, str]]:
    """Collect every clue proposed for a secret word, by players and to the judge.

    Args:
        calls: The calls.

    Returns:
        The pairs of word and clue, both lowercase.
    """
    words = secret_words(calls)
    pairs = set()

    for call in calls:
        word = words.get(call.trace_id)
        clue = None

        if call.agent == "judge":
            match = re.match(r"Secret word: (.+)\nClue: (.+)", call.task)

            if match:
                word, clue = match.groups()
        elif player_phase(call) is GamePhase.CLUE:
            clue = answer_field(output=call.output, field="clue")

        if word and clue and clue.strip():
            pairs.add((word.strip().casefold(), clue.strip().casefold()))

    return pairs


def load_labels(path: Path = LABELS_PATH) -> list[ClueLabel]:
    """Read the label file.

    Args:
        path: The label file.

    Returns:
        The labels, empty when the file does not exist yet.
    """
    if not path.exists():
        return []

    return [ClueLabel.model_validate(item) for item in yaml.safe_load(path.read_text())]


def save_labels(*, labels: list[ClueLabel], path: Path = LABELS_PATH) -> None:
    """Write the label file, sorted by word and clue.

    Args:
        labels: The labels.
        path: The label file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [
        label.model_dump(exclude_none=True)
        | {"legal": label.legal, "synonym": label.synonym}
        for label in sorted(labels, key=lambda label: (label.word, label.clue))
    ]
    body = yaml.safe_dump(items, sort_keys=False, allow_unicode=True, width=88)
    path.write_text(f"{LABELS_HEADER}\n{body}")


@dataclass(frozen=True, slots=True)
class PlayerTurn:
    """A first-attempt player turn rebuilt from the logs.

    Attributes:
        view: The view of the turn.
        word: The secret word of the game.
        said_word: Whether the logged answer said the secret word.
    """

    view: PlayerView
    word: str
    said_word: bool


def parse_view(*, call: LoggedCall, renderer: PlayerPromptRenderer) -> PlayerView | None:
    """Rebuild the view of a first-attempt player turn from its logged prompt.

    Args:
        call: A call of a player in a phase of `TURN_PATTERNS`.
        renderer: The production prompt renderer.

    Returns:
        The view, or `None` when the prompt is of another phase or a retry, or when the
        parsed view does not render to exactly the logged prompt.
    """
    phase = player_phase(call)
    pattern = TURN_PATTERNS.get(phase) if phase else None
    turn = re.match(pattern, call.task) if pattern else None
    instruction = call.instruction

    if (
        phase is None
        or turn is None
        or instruction is None
        or "was rejected" in call.task
    ):
        return None

    try:
        view = view_from_instruction(
            game_id=call.trace_id,
            instruction=instruction,
            phase=phase,
            round_=int(turn[1]) if turn.groups() else None,
        )
    except (KeyError, ValueError):
        return None

    task = renderer.task(view=view, include_schema="JSON schema" in call.task)

    return (
        view if (renderer.instruction(view), task) == (instruction, call.task) else None
    )


def said_word(*, call: LoggedCall, word: str) -> bool:
    """Check whether the logged answer of a clue or discussion turn said the word.

    Uses the rules of the engine: a clue says the word when it contains it after
    normalisation, a statement when it mentions it as a whole word.

    Args:
        call: A player call.
        word: The secret word.

    Returns:
        `True` when the answer said the word.
    """
    clue = answer_field(output=call.output, field="clue")
    statement = answer_field(output=call.output, field="statement")

    if clue is not None:
        return normalize_word(word) in normalize_word(clue)

    return statement is not None and mentions_word(text=statement, word=word)


def player_turns(
    *, calls: list[LoggedCall], renderer: PlayerPromptRenderer
) -> list[PlayerTurn]:
    """Rebuild every first-attempt turn of the evaluated phases, each turn once.

    Args:
        calls: The logged calls.
        renderer: The production prompt renderer.

    Returns:
        The turns, in the order of the logs.
    """
    words = secret_words(calls)
    turns: dict[tuple[str, int, GamePhase, int | None], PlayerTurn] = {}

    for call in calls:
        view = parse_view(call=call, renderer=renderer)
        word = words.get(call.trace_id)

        if view is None or word is None:
            continue

        key = (view.game_id, view.seat, view.phase, view.round)
        turns.setdefault(
            key,
            PlayerTurn(view=view, word=word, said_word=said_word(call=call, word=word)),
        )

    return list(turns.values())


def section(*, text: str, heading: str) -> list[str]:
    """List the lines of one `## heading` section of a rendered instruction.

    Args:
        text: The instruction.
        heading: The heading without the `## `.

    Returns:
        The non-empty lines up to the next heading.
    """
    match = re.search(rf"^## {heading}\n(.*?)(?=^#|\Z)", text, flags=re.M | re.S)

    return [line for line in match.group(1).splitlines() if line] if match else []


def required_match(*, pattern: str, text: str, full: bool = False) -> re.Match[str]:
    """Match a pattern that a rendered instruction must contain.

    Args:
        pattern: The regular expression, matched per line (`re.M`).
        text: The text to search.
        full: Whether the pattern must match the whole text instead of a part of it.

    Returns:
        The match.

    Raises:
        ValueError: When the text does not match.
    """
    match = re.fullmatch(pattern, text) if full else re.search(pattern, text, re.M)

    if match is None:
        message = f"The text does not match the pattern {pattern!r}."
        raise ValueError(message)

    return match


def imposter_name(instruction: str) -> str:
    """Read the name of an imposter from its instruction.

    Args:
        instruction: The rendered instruction of an imposter.

    Returns:
        The name.
    """
    return required_match(
        pattern=r"You are (.+), (?:the|an) imposter\.", text=instruction
    )[1]


def seats_by_name(instruction: str) -> dict[str, int]:
    """Read the seats from the turn order line of an instruction.

    Args:
        instruction: The rendered instruction.

    Returns:
        The seat of each player name.
    """
    line = required_match(pattern=r"^Players in turn order: (.+)\.$", text=instruction)[1]

    return {
        name.removesuffix(" (you)"): seat for seat, name in enumerate(line.split(", "))
    }


def name_list(*, text: str, seats: dict[str, int]) -> list[int]:
    """Turn a list of names joined by commas into seats.

    Args:
        text: The names, such as `Alice, Bob`.
        seats: The seat of each name.

    Returns:
        The seats.
    """
    return [seats[name] for name in text.split(", ")]


def parse_rules(instruction: str) -> GameRules:
    """Read the numbers of the rules from an instruction.

    Args:
        instruction: The rendered instruction.

    Returns:
        The rules.
    """
    imposters = required_match(
        pattern=r"Every player except (one|\d+) knows", text=instruction
    )[1]
    clue_rounds = required_match(
        pattern=r"Clues: there (?:is 1 round|are (\d+) rounds)", text=instruction
    )
    discussion = re.search(
        r"Discussion: there (?:is 1 round|are (\d+) rounds)\..*?at most (\d+) words",
        instruction,
    )

    return GameRules(
        player_count=int(
            required_match(pattern=r"game with (\d+) players", text=instruction)[1]
        ),
        imposter_count=1 if imposters == "one" else int(imposters),
        clue_rounds=int(clue_rounds[1] or 1),
        discussion_rounds=int(discussion[1] or 1) if discussion else 0,
        statement_word_cap=int(discussion[2]) if discussion else 100,
        reasoning_word_cap=int(
            required_match(
                pattern=r"private reasoning of at most (\d+) words", text=instruction
            )[1]
        ),
    )


def parse_clues(*, instruction: str, seats: dict[str, int]) -> list[PublicClue]:
    """Read the clues section of an instruction.

    Args:
        instruction: The rendered instruction.
        seats: The seat of each name.

    Returns:
        The clues.
    """
    clues = []

    for line in section(text=instruction, heading="Clues"):
        match = required_match(
            pattern=r'- Round (\d+), (.+?): (?:"(.*)"|passed)', text=line, full=True
        )
        clues.append(PublicClue(round=int(match[1]), seat=seats[match[2]], clue=match[3]))

    return clues


def parse_statements(*, instruction: str, seats: dict[str, int]) -> list[PublicStatement]:
    """Read the discussion section of an instruction.

    Args:
        instruction: The rendered instruction.
        seats: The seat of each name.

    Returns:
        The statements.
    """
    statements = []

    for line in section(text=instruction, heading="Discussion"):
        match = required_match(
            pattern=(
                r'- Round (\d+), (.+?): (?:"(.*)"( \(cut at the word limit\))?'
                r"|said nothing)"
            ),
            text=line,
            full=True,
        )
        statements.append(
            PublicStatement(
                round=int(match[1]),
                seat=seats[match[2]],
                statement=match[3] or "",
                truncated=match[4] is not None,
            )
        )

    return statements


def parse_votes(*, instruction: str, seats: dict[str, int]) -> VoteResult | None:
    """Read the votes section of an instruction.

    Args:
        instruction: The rendered instruction.
        seats: The seat of each name.

    Returns:
        The revealed votes, or `None` before the votes are revealed.
    """
    lines = section(text=instruction, heading="Votes")
    votes = []
    caught = []

    for line in lines:
        if line.startswith("Caught: "):
            names = line.removeprefix("Caught: ").removesuffix(".")
            tie = names == "nobody, the vote was a tie"
            caught = [] if tie else name_list(text=names, seats=seats)
            continue

        match = required_match(pattern=r"- (.+) voted for (.+)", text=line, full=True)
        votes.append(
            PublicVote(
                voter=seats[match[1]],
                target=None if match[2] == "nobody" else seats[match[2]],
            )
        )

    return VoteResult(votes=votes, caught=caught) if lines else None


def parse_reveal(
    *, instruction: str, seats: dict[str, int], category: str | None
) -> GameReveal | None:
    """Read the reveal section of an instruction.

    Args:
        instruction: The rendered instruction.
        seats: The seat of each name.
        category: The category shown in the instruction, if any.

    Returns:
        The reveal, or `None` before the outcome is decided.
    """
    text = "\n".join(section(text=instruction, heading="Reveal"))

    if not text:
        return None

    said = re.search(
        r"^(.+) said the secret word, which ended the game at once\.$", text, re.M
    )
    secret = required_match(
        pattern=(
            r'^The secret word was "(.+)"\. '
            r"The (?:imposter was|imposters were) (.+)\.$"
        ),
        text=text,
    )
    outcomes = {text: outcome for outcome, text in OUTCOME_TEXTS.items()}

    return GameReveal(
        word=secret[1],
        category=category,
        imposters=name_list(text=secret[2], seats=seats),
        guesses=[
            PublicGuess(seat=seats[match[1]], guess=match[2], correct=match[3] == "right")
            for match in re.finditer(
                r'^(.+) guessed "(.*)", which was (right|wrong)\.$', text, re.M
            )
        ],
        outcome=outcomes[required_match(pattern=r"^Outcome: (.+)\.$", text=text)[1]],
        word_said_by=seats[said[1]] if said else None,
    )


def parse_scratchpad(instruction: str) -> list[ScratchpadEntry]:
    """Read the private notes section of an instruction.

    Args:
        instruction: The rendered instruction.

    Returns:
        The scratchpad entries.
    """
    entries = []

    for line in section(text=instruction, heading="Your private notes"):
        match = required_match(
            pattern=r"- (\w+)(?: round (\d+))?: you (.+?)\. Your reasoning: (.*)",
            text=line,
            full=True,
        )
        entries.append(
            ScratchpadEntry(
                phase=GamePhase(match[1].lower()),
                round=int(match[2]) if match[2] else None,
                action=match[3],
                private_reasoning="" if match[4] == "none" else match[4],
            )
        )

    return entries


def view_from_instruction(
    *, game_id: str, instruction: str, phase: GamePhase, round_: int | None
) -> PlayerView:
    """Parse the view of a turn from the instruction rendered for it.

    Args:
        game_id: The id to give the game.
        instruction: The rendered instruction, as the templates in
            `src/imposter/players/prompts/` write it.
        phase: The phase of the turn.
        round_: The round of the turn, if the phase has rounds.

    Returns:
        The view.

    Raises:
        ValueError: When a required part of the instruction is missing.
        KeyError: When the instruction names a player that does not sit at the table.
    """
    seats = seats_by_name(instruction)
    civilian = re.search(
        r'You are (.+), a civilian\. The secret word is "(.+)"\.', instruction
    )
    name = civilian[1] if civilian else imposter_name(instruction)
    hint = re.search(
        r'Your hint, a word related to the secret word, is "(.+)"\.', instruction
    )
    category_match = re.search(
        r'The category of the secret word is "(.+)"\.', instruction
    )
    category = category_match[1] if category_match else None
    reveal = parse_reveal(instruction=instruction, seats=seats, category=category)

    return PlayerView(
        game_id=game_id,
        phase=phase,
        round=round_,
        rules=parse_rules(instruction),
        seat=seats[name],
        name=name,
        role=PlayerRole.CIVILIAN if civilian else PlayerRole.IMPOSTER,
        word=civilian[2] if civilian else (reveal.word if reveal else None),
        hint=hint[1] if hint else None,
        category=category,
        players=[PublicSeat(seat=seat, name=name) for name, seat in seats.items()],
        clues=parse_clues(instruction=instruction, seats=seats),
        statements=parse_statements(instruction=instruction, seats=seats),
        vote_result=parse_votes(instruction=instruction, seats=seats),
        reveal=reveal,
        scratchpad=parse_scratchpad(instruction),
    )


def is_holdout(word: str) -> bool:
    """Decide by a stable hash of the word whether its cases belong to the holdout set.

    Args:
        word: The secret word.

    Returns:
        `True` for about `HOLDOUT_SHARE` of the words.
    """
    digest = hashlib.sha256(word.casefold().encode()).digest()

    return digest[0] < HOLDOUT_SHARE * 256


def case_id(*parts: str) -> str:
    """Make an eval case id of lowercase words joined by dashes.

    Args:
        *parts: The parts of the id.

    Returns:
        The id.
    """
    return "-".join(
        re.sub(r"[^a-z0-9]+", "_", part.casefold()).strip("_") for part in parts
    )


def user_message(text: str) -> types.Content:
    """Wrap a text as a user message.

    Args:
        text: The text.

    Returns:
        The message.
    """
    return types.Content(role="user", parts=[types.Part(text=text)])


def judge_case(label: ClueLabel) -> EvalCase:
    """Make the eval case of one labelled clue for the judge.

    The expected answer holds only the verdict, which `verdict_match` compares.

    Args:
        label: A labelled clue.

    Returns:
        The case, with the word and clue in the session state.
    """
    kind = "synonym" if label.synonym else ("legal" if label.legal else "illegal")

    return EvalCase(
        eval_id=case_id(kind, label.word, label.clue),
        conversation=[
            Invocation(
                user_content=user_message(
                    VALID_CLUE_TASK.format(word=label.word, clue=label.clue)
                ),
                final_response=types.Content(
                    role="model",
                    parts=[types.Part(text=json.dumps({"verdict": label.legal}))],
                ),
            )
        ],
        session_input=SessionInput(
            app_name=JUDGE_DIR.name,
            user_id=EVAL_USER,
            state={"word": label.word, "clue": label.clue},
        ),
    )


def player_case(
    *, turn: PlayerTurn, suite: str, renderer: PlayerPromptRenderer, repeat: int = 0
) -> EvalCase:
    """Make the eval case of one player turn.

    The user message of the case is the full prompt, instruction and task, so that the
    graders of the rubric metric see the game. The eval agent does not send it: it renders
    the prompts again from the view in the session state.

    Args:
        turn: The turn.
        suite: The eval set kind, a key of `QUALITY_RUBRICS` or `word_said`.
        renderer: The production prompt renderer.
        repeat: The number of the repetition of a hard case, 0 for a normal case.

    Returns:
        The case, with the quality rubric of the suite (if any), and the view and the
        secret word as rubrics for the custom metrics, which do not see the state.
    """
    view = turn.view
    parts = [turn.word, view.game_id[:8], view.name, f"{view.phase} {view.round or ''}"]
    rubric = QUALITY_RUBRICS.get(suite)
    rubrics = [
        Rubric(
            rubric_id="player_view",
            rubric_content=RubricContent(text_property=view.model_dump_json()),
            type=PLAYER_VIEW_RUBRIC_TYPE,
        ),
        Rubric(
            rubric_id="secret_word",
            rubric_content=RubricContent(text_property=turn.word),
            type=SECRET_WORD_RUBRIC_TYPE,
        ),
    ]

    if rubric is not None:
        rubrics.append(
            Rubric(
                rubric_id=suite,
                rubric_content=RubricContent(text_property=rubric.format(word=turn.word)),
                type=QUALITY_RUBRIC_TYPE,
            )
        )

    return EvalCase(
        eval_id=case_id(*parts, *([f"repeat {repeat}"] if repeat else [])),
        conversation=[
            Invocation(
                user_content=user_message(
                    f"{renderer.instruction(view)}\n\n{renderer.task(view=view)}"
                )
            )
        ],
        session_input=SessionInput(
            app_name=PLAYER_DIRS[view.phase].name,
            user_id=EVAL_USER,
            state={"view": view.model_dump(mode="json")},
        ),
        rubrics=rubrics,
    )


def player_suites(
    turns: list[PlayerTurn],
) -> dict[tuple[GamePhase, str], list[PlayerTurn]]:
    """Group the turns into the eval sets of the player evals.

    Args:
        turns: The turns.

    Returns:
        The turns of each eval app phase and suite.
    """
    clue = [turn for turn in turns if turn.view.phase is GamePhase.CLUE]
    discussion = [turn for turn in turns if turn.view.phase is GamePhase.DISCUSSION]

    return {
        (GamePhase.CLUE, "civilian"): [
            turn for turn in clue if turn.view.role is PlayerRole.CIVILIAN
        ],
        (GamePhase.CLUE, "imposter"): [
            turn for turn in clue if turn.view.role is PlayerRole.IMPOSTER
        ],
        (GamePhase.CLUE, "word_said"): [turn for turn in clue if turn.said_word],
        (GamePhase.DISCUSSION, "statement"): discussion,
        (GamePhase.DISCUSSION, "word_said"): [
            turn for turn in discussion if turn.said_word
        ],
        (GamePhase.DEBRIEF, "reflection"): [
            turn for turn in turns if turn.view.phase is GamePhase.DEBRIEF
        ],
    }


def save_eval_set(*, eval_set: EvalSet, path: Path) -> None:
    """Write an eval set as JSON.

    Args:
        eval_set: The eval set.
        path: The file.
    """
    data: dict[str, Any] = eval_set.model_dump(mode="json", exclude_none=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    logger.info("Wrote %d cases to %s.", len(eval_set.eval_cases), path)


app = typer.Typer(add_completion=False, no_args_is_help=True)
RawDirOption = Annotated[Path, typer.Option(help="Folder with the exports.")]


@app.callback()
def main() -> None:
    """Build the ADK eval sets of `evals/` from exported games and labels."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")


@app.command()
def labels(raw_dir: RawDirOption = RAW_DIR) -> None:
    """Add every clue proposed in the exported games to the labels, unlabelled."""
    existing = load_labels()
    known = {(label.word, label.clue) for label in existing}
    new = [
        ClueLabel(word=word, clue=clue)
        for word, clue in clue_pairs(logged_calls(raw_dir))
        if (word, clue) not in known
    ]
    save_labels(labels=existing + new)
    logger.info("Added %d new clues, %d labels in total.", len(new), len(existing + new))


@app.command()
def judge() -> None:
    """Build the judge eval set from the labelled clues the code checks do not decide."""
    cases = [
        judge_case(label)
        for label in load_labels()
        if label.legal is not None
        and clue_check(clue=label.clue, word=label.word) is None
    ]
    save_eval_set(
        eval_set=EvalSet(
            eval_set_id="clue_labels", name="Labelled clues", eval_cases=cases
        ),
        path=JUDGE_DIR / "clue_labels.evalset.json",
    )


@app.command()
def players(raw_dir: RawDirOption = RAW_DIR) -> None:
    """Build the eval sets of the clue, discussion and debrief turns."""
    renderer = PlayerPromptRenderer()
    calls = logged_calls(raw_dir)
    turns = player_turns(calls=calls, renderer=renderer)
    logger.info("Rebuilt %d player turns from %d logged calls.", len(turns), len(calls))

    for (phase, suite), members in player_suites(turns).items():
        folder = PLAYER_DIRS[phase]

        if suite == "word_said":
            cases = [
                player_case(turn=turn, suite=suite, renderer=renderer, repeat=repeat)
                for turn in members
                for repeat in range(1, WORD_SAID_REPEATS + 1)
            ]
            splits = {suite: cases}
        else:
            splits = {
                f"{suite}_{split}": [
                    player_case(turn=turn, suite=suite, renderer=renderer)
                    for turn in members
                    if is_holdout(turn.word) is (split == "holdout")
                ]
                for split in ("dev", "holdout")
            }

        for eval_set_id, cases in splits.items():
            save_eval_set(
                eval_set=EvalSet(eval_set_id=eval_set_id, eval_cases=cases),
                path=folder / f"{eval_set_id}.evalset.json",
            )


if __name__ == "__main__":
    app()
