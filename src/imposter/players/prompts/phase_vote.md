It is time to vote, {{ view.name }}. The votes are secret until everyone has voted.

Vote for the one other player you think is {{ "the imposter" if view.rules.imposter_count == 1 else "an imposter" }}. Use their exact name, one of: {{ others | join(", ") }}. You cannot vote for yourself. Also write your private reasoning about this vote, at most {{ view.rules.reasoning_word_cap }} words.
{% include "response.md" %}
