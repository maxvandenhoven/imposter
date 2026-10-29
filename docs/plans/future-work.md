# Future work

Not planned in any milestone, but the design keeps these possible.

## Personas

Give players a play style on top of their model.

- `players/personas.yaml`: entries `{id, label, style_prompt}`, for example `cautious`
  ("Give safe, generic clues; accuse only with strong evidence"), `aggressive` ("Accuse
  early and push others to justify themselves"), `chaotic`, `analytical`, `quiet`.
- `PlayerConfig.persona: str | None` already exists (README D23). When set, the persona's
  `style_prompt` is rendered into the `persona.md` slot of the instruction.
- Setup screen: a persona dropdown per seat (default none) and "random personas".
- Span attribute `imposter.player.persona`; the tournament CLI can group by persona.
- Interesting questions: does persona dominate model? Do aggressive players get voted out
  more often as civilians?

## A2A remote players

An `A2aPlayer` implementing the `PlayerProtocol` by calling a remote agent over the A2A
protocol (ADK has A2A support: `to_a2a` to expose, a remote A2A agent to consume). Each
"player service" could run on its own Cloud Run service or another cloud, even built with a
different framework. The `GameRunnerAgent` and engine stay unchanged, and `PlayerView` and the
structured responses become the A2A message schema. Trace context propagates over HTTP so
remote turns still nest under the game trace.

## Agent Engine deployment comparison

Deploy the same `GameRunnerAgent` to Vertex AI Agent Engine (Agent Runtime) with
`agents-cli deploy` or the SDK, run games headless through it, and compare with Cloud Run:
setup effort, managed sessions, built-in tracing, cold starts, cost. The UI would stay on
Cloud Run and call Agent Engine, or the CLI drives it directly.

## Persistence and analytics

- A Firestore adapter for `GameStoreProtocol` and the event log (one document per game, `events` subcollection).
- Pub/Sub or Firestore listeners as an `EventBusProtocol` adapter for multiple instances.
- Vertex AI or database `SessionService`.
- BigQuery Agent Analytics plugin and GCS completion upload; a leaderboard page (model win
  rates as imposter and civilian, detection accuracy) over persisted games.
- Past games list in the UI.

## Concurrent games

Lift the one-game limit: per-game buses already isolate games. Needs quota awareness
(Model Garden 429s) and possibly a queue.

## Multi-imposter UI polish

Engine supports `k` imposters (`game-rules.md`); the UI needs team display, multiple
guesses and outcome copy.

## Laya judge on Cloud Run

The Laya typed-decision model (421M parameters, Apache-2.0, yes/no and choice outputs with
probabilities) is only available as a self-deployed model in Model Garden. Alternative:
package it in a second Cloud Run service on CPU (2–4 GiB), scaling to zero, called with
service-to-service IAM auth, behind a `LayaJudge` adapter. Compare its verdicts with the
Gemini judge on the same games.

## ADK eval framework

`adk eval` / `agents-cli eval` with eval sets per phase (for example "civilian clue does
not reveal the word", "imposter guess quality") and LLM-as-judge metrics, complementing the
tournament CLI.

## Graph Workflow version of the GameRunnerAgent

Re-express the game loop with ADK 2.x's graph `Workflow` API and compare readability and
traces with the custom `BaseAgent`.

## CI/CD

GitHub Actions running `make check test`, and deploy on merge to `main` with Workload
Identity Federation (no service account keys), the pool and provider managed in Terraform.

## More

- Human player seat (play against the agents in the browser).
- OpenAI models through LiteLLM with a key in Secret Manager (dropped in v1, README D5).
- Voice: read clues and statements aloud.
