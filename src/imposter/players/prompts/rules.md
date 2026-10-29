# Game rules

You are playing Imposter, a social deduction word game with {{ rules.player_count }} players.

{% if rules.imposter_count == 1 %}
Every player except one knows the same secret word. These players are the civilians. The remaining player is the imposter and does not know the word.
{% else %}
Every player except {{ rules.imposter_count }} knows the same secret word. These players are the civilians. The other {{ rules.imposter_count }} players are imposters, do not know the word and do not know who the other imposters are.
{% endif %}

Two rules matter more than any other:

- **Never say the secret word.** Whoever says it in a clue or a statement, even as part of a longer word or by accident, loses the game for their side on the spot, and the game ends immediately. If a civilian says it, the imposters win. If an imposter says it, the civilians win.
- **Never repeat a clue.** A clue must be a word that nobody has given yet, including you. A repeated clue is rejected.

The game is played in phases:

1. Clues: there {{ "is 1 round" if rules.clue_rounds == 1 else "are %d rounds" % rules.clue_rounds }}. In each round every player, in turn order, gives exactly one word as a clue that is related to the secret word. A clue that breaks the rules is replaced by a pass.
{% if rules.discussion_rounds %}
2. Discussion: there {{ "is 1 round" if rules.discussion_rounds == 1 else "are %d rounds" % rules.discussion_rounds }}. In each round every player, in turn order, makes a public statement of at most {{ rules.statement_word_cap }} words to accuse, defend or question.
{% endif %}
{{ "3" if rules.discussion_rounds else "2" }}. Vote: every player votes in secret for one other player. The votes are revealed together. The player{{ "s" if rules.imposter_count > 1 }} with the most votes {{ "are" if rules.imposter_count > 1 else "is" }} caught, and a tie catches nobody.
{{ "4" if rules.discussion_rounds else "3" }}. Guess: every imposter makes one guess at the secret word. This is the only moment anyone may say it.
{{ "5" if rules.discussion_rounds else "4" }}. Outcome: an imposter who is not caught wins. A caught imposter who guesses the word steals the win. Otherwise the civilians win.
{{ "6" if rules.discussion_rounds else "5" }}. Debrief: the word and the roles are revealed, and every player reflects on how they played.

With every action you also record private reasoning of at most {{ rules.reasoning_word_cap }} words. Nobody else ever sees it, but you will see your own earlier reasoning in later turns.
