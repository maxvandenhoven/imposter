"""The clue judge as `adk eval` and `adk optimize` see it.

The root agent is the production judge's `LlmAgent` itself: the instruction of
`JUDGE_INSTRUCTION` and the structured `JudgeAnswer`. Each eval case sends the clue task
(`VALID_CLUE_TASK`) as the user message, rendered by `scripts/build_evalsets.py judge`.
The code checks that run before the model in production are tested separately against
the same labels (`tests/evals/test_clue_labels.py`).
"""

from imposter.judge.llm_judge import LlmJudge

root_agent = LlmJudge().agent.runner.agent
