"""The debrief agent of a player as `adk eval` sees it, see `evals/player_turn.py`."""

from player_turn import player_eval_agent

from imposter.config import GamePhase

root_agent = player_eval_agent(GamePhase.DEBRIEF)
