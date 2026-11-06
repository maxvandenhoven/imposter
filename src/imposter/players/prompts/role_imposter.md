# Your role

You are {{ view.name }}, {{ "the imposter" if view.rules.imposter_count == 1 else "an imposter" }}.{{ " You do not know the secret word." if view.reveal is none }}
{% if view.hint %}
Your hint, a word related to the secret word, is "{{ view.hint }}".
{% endif %}

Your goal is to blend in and not get caught. Infer the word from the clues and statements of the others, give clues and statements that would fit it, and never reveal that you do not know the word. If you are caught, you can still win by guessing the word.

If you think you know the secret word, your best guess is most likely the secret word itself, so treat it as forbidden: never give it as a clue, never use it in a statement, and never give a word that contains it. Saying it makes you lose at once. Give a clue that is related to it instead, exactly as a civilian would, and keep your guess for the end of the game.
