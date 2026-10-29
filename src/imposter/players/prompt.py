import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from imposter.config import GameOutcome, PlayerRole
from imposter.engine.views import PlayerView, other_players
from imposter.players.base import PHASE_RESPONSE_TYPES

PROMPTS_DIR = Path(__file__).with_name("prompts")
"""The Jinja2 templates of the player prompts."""

INSTRUCTION_TEMPLATES = ("rules.md", "persona.md", "{role}.md", "transcript.md")
"""The templates of the instruction, in order. `{role}` is the template of the role."""

ROLE_TEMPLATES: dict[PlayerRole, str] = {
    PlayerRole.CIVILIAN: "role_civilian",
    PlayerRole.IMPOSTER: "role_imposter",
}
"""The role template of each role, without extension."""

OUTCOME_TEXTS: dict[GameOutcome, str] = {
    GameOutcome.IMPOSTER_WINS: "the imposter was not caught and wins",
    GameOutcome.IMPOSTER_STEALS: "the imposter was caught but guessed the word and wins",
    GameOutcome.CIVILIANS_WIN: "the civilians win",
}
"""How the outcome is told in the reveal."""


class PlayerPromptRenderer:
    """Renders the prompts of a seat from its view, with the templates in `prompts/`.

    The system instruction is fixed text. The instruction holds what stays true during
    a turn: the rules, the persona, the role and the game so far. The task holds what
    the seat must do now, the reason a previous attempt was rejected and, for models
    without native structured output, the JSON schema of the answer. Both are rendered
    only from the view, so a seat's prompt can never contain more than the view.

    Attributes:
        environment: The Jinja2 environment that loads the templates.
    """

    def __init__(self, prompts_dir: Path = PROMPTS_DIR) -> None:
        """Initialize the renderer.

        Args:
            prompts_dir: The directory of the templates.
        """
        self.environment = Environment(
            loader=FileSystemLoader(prompts_dir),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )

    def system(self) -> str:
        """Render the system instruction, the same for every seat and turn.

        Returns:
            The system instruction.
        """
        return self.environment.get_template("system.md").render().strip()

    def instruction(self, view: PlayerView) -> str:
        """Render the instruction of a seat: rules, persona, role and the game so far.

        Args:
            view: Everything the seat may know.

        Returns:
            The instruction, with empty parts left out.
        """
        role = ROLE_TEMPLATES[view.role]
        parts = [
            self.render(name=template.format(role=role), view=view)
            for template in INSTRUCTION_TEMPLATES
        ]

        return "\n\n".join(part for part in parts if part)

    def task(
        self,
        *,
        view: PlayerView,
        retry_reason: str | None = None,
        include_schema: bool = False,
    ) -> str:
        """Render the task of a seat in the phase of its view.

        Args:
            view: Everything the seat may know.
            retry_reason: Why the previous attempt in this turn was rejected, if any.
            include_schema: Whether to ask for JSON matching the response schema, for
                models without native structured output.

        Returns:
            The task.

        Raises:
            ValueError: When players do not act in the phase of the view.
        """
        response_type = PHASE_RESPONSE_TYPES.get(view.phase)

        if response_type is None:
            message = f"Players do not act in phase {view.phase}."
            raise ValueError(message)

        schema = None

        if include_schema:
            # The class docstring describes the code, not the answer, so it is left out.
            schema_dict = response_type.model_json_schema()
            schema_dict.pop("description", None)
            schema = json.dumps(schema_dict)

        return self.render(
            name=f"phase_{view.phase}.md",
            view=view,
            retry_reason=retry_reason,
            response_schema=schema,
        )

    def render(self, *, name: str, view: PlayerView, **context: Any) -> str:
        """Render one template with the view and the names derived from it.

        Args:
            name: The template file name.
            view: Everything the seat may know.
            **context: Extra template variables.

        Returns:
            The rendered text, stripped.
        """
        template = self.environment.get_template(name)
        text = template.render(
            view=view,
            rules=view.rules,
            names={player.seat: player.name for player in view.players},
            others=[player.name for player in other_players(view)],
            outcomes=OUTCOME_TEXTS,
            **{"retry_reason": None, "response_schema": None, **context},
        )

        return text.strip()
