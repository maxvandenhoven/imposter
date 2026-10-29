It is clue round {{ view.round }} of {{ view.rules.clue_rounds }} and your turn, {{ view.name }}.

Give exactly one word as your clue, related to the secret word. Do not say the secret word itself or a word that contains it: that loses the game for your side at once.
{% if view.clues | selectattr("clue") | list %}

Words already used as clues, which you must not repeat (this includes your own): {{ view.clues | selectattr("clue") | map(attribute="clue") | join(", ") }}.
{% endif %}

Also write your private reasoning about this clue, at most {{ view.rules.reasoning_word_cap }} words.
{% include "response.md" %}
