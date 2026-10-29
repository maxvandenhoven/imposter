It is clue round {{ view.round }} of {{ view.rules.clue_rounds }} and your turn, {{ view.name }}.

Give exactly one word as your clue. It must not be the secret word, must not contain it and must not repeat a clue that was already given. Also write your private reasoning about this clue, at most {{ view.rules.reasoning_word_cap }} words.
{% include "response.md" %}
