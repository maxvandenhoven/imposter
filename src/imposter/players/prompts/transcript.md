# The game so far

Players in turn order: {% for player in view.players %}{{ player.name }}{{ " (you)" if player.seat == view.seat }}{{ ", " if not loop.last }}{% endfor %}.
{% if view.category %}
The category of the secret word is "{{ view.category }}".
{% endif %}
{% if view.clues %}

## Clues

{% for clue in view.clues %}
- Round {{ clue.round }}, {{ names[clue.seat] }}: {{ '"%s"' % clue.clue if clue.clue else "passed" }}
{% endfor %}
{% endif %}
{% if view.statements %}

## Discussion

{% for statement in view.statements %}
- Round {{ statement.round }}, {{ names[statement.seat] }}: {{ '"%s"' % statement.statement if statement.statement else "said nothing" }}{{ " (cut at the word limit)" if statement.truncated }}
{% endfor %}
{% endif %}
{% if view.vote_result %}

## Votes

{% for vote in view.vote_result.votes %}
- {{ names[vote.voter] }} voted for {{ names[vote.target] if vote.target is not none else "nobody" }}
{% endfor %}

Caught: {% for seat in view.vote_result.caught %}{{ names[seat] }}{{ ", " if not loop.last }}{% else %}nobody, the vote was a tie{% endfor %}.
{% endif %}
{% if view.reveal %}

## Reveal

The secret word was "{{ view.reveal.word }}". The {{ "imposter was" if view.reveal.imposters | length == 1 else "imposters were" }} {% for seat in view.reveal.imposters %}{{ names[seat] }}{{ ", " if not loop.last }}{% endfor %}.
{% for guess in view.reveal.guesses %}
{{ names[guess.seat] }} guessed "{{ guess.guess }}", which was {{ "right" if guess.correct else "wrong" }}.
{% endfor %}
Outcome: {{ outcomes[view.reveal.outcome] }}.
{% endif %}
{% if view.scratchpad %}

## Your private notes

{% for entry in view.scratchpad %}
- {{ entry.phase | capitalize }}{{ " round %d" % entry.round if entry.round }}: you {{ entry.action }}. Your reasoning: {{ entry.private_reasoning or "none" }}
{% endfor %}
{% endif %}
