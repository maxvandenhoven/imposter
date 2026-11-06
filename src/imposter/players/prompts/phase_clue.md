It is clue round {{ view.round }} of {{ view.rules.clue_rounds }} and your turn, {{ view.name }}.

Give exactly one word as your clue, related to the secret word. Do not say the secret word itself or a word that contains it: that loses the game for your side at once.
{% if view.role == "imposter" %}
The clues of the others all point to the secret word, so the most obvious word that fits them all is most likely the secret word itself, even when it feels like a safe, general word. Never give that word, or a word that contains it, as your clue. Give a word one step away from it instead, like the clues of the others.
{% endif %}
{% if view.clues | selectattr("clue") | list %}

Words already used as clues, which you must not repeat (this includes your own): {{ view.clues | selectattr("clue") | map(attribute="clue") | join(", ") }}.
{% endif %}

Also write your private reasoning about this clue in one or two short sentences, at most {{ view.rules.reasoning_word_cap }} words.
{% include "response.md" %}
