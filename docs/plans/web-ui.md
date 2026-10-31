# Web UI and API

## API (ADK's API server, `src/imposter/api/`)

The backend is ADK's own API server (`get_fast_api_app`, what `adk api_server` runs)
serving the game app of `agent.py`, plus one route of ours. `api/app.py` builds it in
single agent mode (the package directory as `agents_dir`), with sessions in memory and
without ADK's dev UI. There are no game routes of our own: a game is an ADK session, and
playing it is an ADK run.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/catalog` | Ours: the models (id, display name, provider, logo, prices), the word categories (name and description, no words) and the default lineup |
| `POST` | `/apps/imposter/users/{user_id}/sessions` | Create a game: the body is `{"state": {"game:request": <GameRequest>}}`. The session id is the game id |
| `POST` | `/run_sse` | Play the game and stream its events. Body: `app_name`, `user_id`, `session_id`, `new_message` (any user message, for example "Play the game."), `"streaming": true` |
| `GET` | `/apps/imposter/users/{user_id}/sessions/{session_id}` | The session with every stored event, for a finished game |
| `GET` | `/traces/{game_id}` | Ours: `{"url": ...}`, the Trace Explorer link of the game's run once it started, or `null` when traces are not sent to Google Cloud. The trace plugin of `agent.py` notes the trace id of each run |
| `GET` | `/health` | Liveness |
| `GET` | `/` | Ours: the built frontend, from `IMPOSTER_FRONTEND_DIR` or `frontend/dist`, when it exists. Mounted after every API route, so unknown API paths stay 404 |

ADK's other routes (artifacts, memory, `/list-apps`, `/run`) are there too and unused.

**Lifecycle.** The game runs inside the `/run_sse` request: it starts when the request
comes in and ends with the stream. When the client goes away, ADK cancels the run and
the game is aborted. This keeps CPU allocated under request-based billing (README D14).
There is no reconnect to a running game: a second run of the session plays nothing and
says the game was already played. A finished game can be loaded from its session.
Invalid options fail when the run starts, with an error event (`errorCode`,
`errorMessage`) in the stream.

**Reading the stream.** Each SSE `data:` line is one ADK event as JSON (camelCase
fields). A client needs three kinds:

- **Engine events.** Events with `customMetadata.game_event` carry one engine event (the
  same JSON as the event log, with `type`, `seq`, `phase`, `round` and the fields of its
  type), in `seq` order without gaps. A `turn_started` event (with `seat`) is sent before
  the player is asked, so it can drive a "thinking" indicator. The answer arrives as the
  engine event of the phase (`clue_given`, `statement_made`, `vote_cast`, `guess_made`,
  `reflection`) after the turn, together with `usage` and any `player_error`.
- **Token deltas.** Events with `partial: true` from author `player_{seat}_{phase}`
  carry the next chunk of the answer being written in `content.parts[].text`. Parts with
  `thought: true` are the model's native thinking, which a client can hide. The text is
  the JSON answer, for example `{"clue": "yel`, so a partial JSON parser shows `clue`,
  `statement` and `private_reasoning` as they grow. Every attempt of a turn has its own
  `nodeInfo.path`, ending in `player_{seat}_{phase}@{attempt}`, so a client starts over
  when a new path appears (a retry). Chunk size depends on the model: Gemini sends a
  few large chunks, Claude and `gpt-oss` many small ones.
- **Errors.** An event with `errorCode` from author `game_runner` means the run failed,
  for example on invalid options, and ADK ends the stream with a last line of the form
  `{"error": "...", "error_details": {...}}`. An `errorCode` event from a
  `player_{seat}_{phase}` author is one failed model attempt, which the game handles: it
  asks again or falls back, and a `player_error` engine event says so.

Everything else (the final event of each model call with its `output`, the output of
each turn node, routing events) can be ignored. Partial events are not stored in the
session, so a finished game loads without them.

- The server sends **all** events including private fields; audience mode hides them in
  the browser. Acceptable because access is limited to the owner via IAP.
- Settings come from the environment: `IMPOSTER_TELEMETRY` (`observability.md`) and the
  Vertex AI variables of `.env.example`.
- `imposter serve` (CLI) runs uvicorn with the app factory
  (`imposter.api.app:create_app`), and `make dev` runs it with reload.

Why no API of our own: the game already runs as an ADK app with the request in session
state, and ADK's server streams its runs over SSE and cancels a run when its client
leaves. Own routes would add a second event stream, replay and reconnect logic that ADK
does not need. What that gives up is reconnecting to a running game.

## Frontend (`frontend/`)

A single-page React app in `frontend/` at the repo root, with the stack and tooling of the
hive repo (`maxvandenhoven/hive`, see its `docs/plans/frontend.md`). It is built to static
files, which the API app serves at `/` after ADK's routes, so one container and one origin
serve both.

| Concern | Choice |
|---|---|
| Build | Vite + React + TypeScript (strict, `noUncheckedIndexedAccess`), Node pinned in `.nvmrc` |
| Package manager | npm, lockfile committed |
| Styling | Tailwind CSS through `@tailwindcss/vite`, with a light "game night" theme in the shadcn theme tokens of `index.css` (warm paper, a violet table and one colour each for speaking, imposter and civilian), Geist for text and Bricolage Grotesque for headings |
| Components | shadcn/ui (Radix base, Lucide icons), copied into `frontend/src/components/ui/` and themed. App components build on them |
| Animation | `motion` for chips, bubbles, the vote reveal and layout changes, with `prefers-reduced-motion` respected |
| Server state | TanStack Query for the catalog |
| API types | `imposter openapi` writes the app's OpenAPI schema, with the `GameRequest` and engine event schemas added because ADK types the session state and `custom_metadata` as free objects. `make api-client` generates `frontend/src/api/schema.ts` from it with `openapi-typescript` |
| Streaming | `fetch` with a stream reader for `/run_sse` (a `POST`, so not `EventSource`), in a small stream client that sorts the events as §API describes |
| Lint, format, test | ESLint, Prettier, Vitest with Testing Library |

There is no router: the app has a setup view and a board view. In development, `make dev`
runs the API on port 8000 and the Vite dev server on port 5173, which forwards `/catalog`,
`/apps`, `/run_sse` and `/traces` to the API. The proxy keeps the browser's `Host` header
(no `changeOrigin`), because ADK's API server refuses a `POST` whose `Origin` is not the
host it was sent to (found in WP 09). In the image, a Node stage builds `frontend/dist`
(`infrastructure.md` §Build and deploy).

The stream client (`src/api/gameStream.ts`) creates the session for a fixed user id
(`local`). The IAP identity does not go through it: the server reads it from the request header (WP 13). It reports a failed run once: the
`errorCode` event of the game runner when there is one, and otherwise ADK's last error
line. Leaving or stopping the game aborts the fetch, and the server stops the run, but the
stored session then ends without a `game_aborted` event, because the run is cancelled
before it can store one.

Rules that keep the look consistent:

- Every control and surface comes from shadcn/ui. Pages compose app components, app
  components compose the primitives in `components/ui/`, and nothing outside `ui/` styles
  raw buttons, inputs or dialogs.
- Colours, radii and fonts come from the theme tokens, not from one-off values.
- Logic that turns events into what is shown (the board state, the partial answers, the
  playback cursor) lives in plain TypeScript functions in `frontend/src/lib/`, tested
  with Vitest, and components only render it.
- Provider logos are small SVGs in `frontend/public/logos/`, at the paths the catalog's
  `logo` field names. Logos for providers without a catalog model yet (DeepSeek, Grok,
  Mistral, Qwen) are there too, coloured to show on the light theme.
- It works at laptop and projector sizes, and a phone layout is nice to have.

### Setup screen

Kept simple: the essentials up front, the rest under "Advanced".

- Word: tabs for *Random* (category dropdown), *Custom* (typed word and an optional
  category of free text, since a typed word need not fit a catalog category) and
  *Generated* (made up by Gemini Flash-Lite).
- Players: list of seats with a model dropdown each, add/remove (3–8), "randomise
  lineup" and "randomise imposters". Each seat has a mask toggle that makes its player
  an imposter, and the number of masks is the number of imposters, so there is no
  separate imposter count. The form starts with one mask on a random seat. "Randomise
  imposters" moves the masks to random seats and keeps their number, and removing the
  seat of the last imposter moves its mask to a random other seat. The game request
  always names its imposters, and the engine only picks them at random for requests
  that do not, such as those of the CLI. Each seat has a drag handle (and the arrow keys
  on the handle) to move it with its model and mask. The engine still shuffles the seats
  when the game starts, so the order is only for the person setting up.
- Every section, option and advanced field says what it does and what it changes in a
  game, for example that the imposter hint is generated by Gemini Flash-Lite and that
  a temperature override replaces each model's own setting.
- Identity mode: segmented control (Seats / Names / Models).
- Toggles: public category, imposter hint.
- Advanced: clue rounds, discussion rounds, word caps, token budget, temperature
  override.
- The limits are checked in the browser before Start, because invalid options only fail
  once the run starts.
- Layout: one column of about 64rem with a numbered row per section (1. Secret word,
  2. Players, 3. Rules) in one panel, Import and Start below it. The sections grow with
  their content (more seats, other word modes), which made side by side cards end at
  different heights, so each row has its icon, title and introduction in a fixed left
  column and the controls on the right. "How to play" uses the same rows
  (`NumberedSection`), so the titles, controls and diagrams of the whole page start on
  the same vertical lines.
- "How to play" below the form explains each phase with small scenes built from the
  board's own pieces (`components/rules/`): four players in a row with speech bubbles
  pointing at the speaker, word cards, ballots and the "Caught" stamp, with a check for
  an answer that follows the rules and a cross for one that breaks them. A list of the
  ways the game ends closes it.
- Start creates the session with the request in its state, opens the board and starts the
  run on `/run_sse`. Leaving the page during a game aborts it, so the page warns first.

### Game board

- The table card spans the top of the board with the phase, round and category on the
  left, the word in the middle (in god mode, or once revealed) and what the phase is
  about on the right. The players sit in one row below it, in seat order from left to
  right, and the transcript is next to the board. One row scales from 3 to 8 players
  and keeps the turn order visible, which a ring of seats around the table did not do
  well for odd numbers.
- Each player has a column: a card with the name, the model logo and name (the catalog
  display names carry the model version, for example "Claude Haiku 5.5"), the role
  badge (in god mode or after the reveal) and the clue chips per round, then the
  player's answer of the current round as a speech bubble and, below it, the private
  reasoning as a thought bubble. The player whose turn it is glows softly and shows
  typing dots. The model logos show in both modes: the `usage` events name the model of
  each seat publicly anyway, and comparing models is the point of watching.
- In clue, discussion and guess turns, which one player takes alone, the answer is
  written in a large bubble on the table, and when the turn ends the bubble moves down
  into the player's column (a shared `motion` layout). Votes and reflections, which
  every player writes at once, are written in the columns directly.
- Live answers: the partial JSON of the current answer is parsed as it grows
  (`lib/partialJson.ts`), so the clue or statement appears on the table while it is
  written. In audience mode the secret word is masked in live clues and
  statements, including a start of it at the end of the text, because a player who
  says the word only becomes a `secret_word_said` event once the turn ends.
- Timeline/transcript: clues appear as chips per round sliding in, discussion as speech
  bubbles, votes as a reveal sequence of ballots and a vote count popping onto each
  target, the imposter's guess with the judge verdict, and a dark outcome banner lit in
  the winning side's colour, so it stands out from the table card below it.
- Votes as ballots: each vote is a small ballot with the voter's name that flies in an
  arc from the voter's card to the target's card, one after another at the reveal, and
  stays there as a chip, so the cards show who voted for whom. Curved arrows between
  the seats were dropped: two seats voting for each other drew overlapping arrows, and
  the arrows were anchored to the player columns, which grow as the reasoning is
  written, so they drifted down the board. The ballots fly between the cards, which
  keep their place. `player_error`
  warnings sit under the transcript entry of their turn, or stand alone when that turn
  is hidden (a secret vote in audience mode).
- God mode: the word, roles, and each turn's private reasoning shown live as a
  "thought bubble" next to the public action, and the secret votes as dashed ballots as
  they come in. The models' own thought parts are shown collapsed. Audience mode hides
  all of these until the reveal, also in the partial text. After the `outcome` event
  everything is shown in both modes.
- Header: a dark bar across the full width of the page (the scoped `.night` colours in
  `index.css`), with the status and the running token and cost estimate (from the `usage` events
  and the catalog prices) on the left, the phase steps in the middle, and the link to
  the trace in Cloud Trace (from `/traces/{game_id}`), Export, the view settings and
  Stop or New game on the right, with the trace and Export as icon buttons so the header
  keeps to one row. God mode is the "Show hidden info" switch (on by default) in the
  view settings popover, since it is a setting that is rarely changed during a game.
  Every phase step that has ended in the game is a button that jumps the cursor to the
  end of that phase (`phaseEnd` in `lib/table.ts`), so the phase can be discussed. A
  step the game went past without playing it, such as the vote and the guess of a game
  that ended when the word was said, shows a skip icon and a struck through label in
  amber instead of the blue check of a done step.
- `lib/boardView.ts` builds all of this as one view model from the events up to a
  cursor, the partial answers and the mode, and its tests check that audience mode shows
  nothing private at any cursor before the reveal.

### Playback

A game plays faster than an audience can follow, and models stream unevenly (Gemini
sends a few large chunks, Claude many small ones). So the board does not show the stream
as it arrives. Everything the stream sends, the engine events and each growing answer,
is appended to a timeline in the browser (`GameTimeline` in `lib/playback.ts`), and a
playback (`GamePlayback`) plays it at a pace the audience can follow, driven by an
animation frame clock.

- Each item takes a time at normal speed. An answer takes the time its new characters
  need at 30 characters a second, slow enough to read along, so every model is written
  out at the same smooth rate, and the model's own thinking takes no time. An engine
  event shows at once and then pauses so it can be read: 2 s for a new phase or round
  and for a clue, a statement 1.5 s plus 0.12 s a word (up to 6 s), the vote reveal 3 s
  plus 0.8 s a vote (so the ballots can fly), the guess 4 s and the outcome 6 s.
- When the timeline is ahead of the playback, after a pause or because the pauses add
  up, answers are written faster, smoothly and in proportion to the backlog, up to twice
  as fast once more than 20 s are waiting. The pauses to read are never shortened by
  the catch up, only by the chosen speed, so the vote, the guess and the outcome keep
  their time after a long discussion. The board never shows a backlog at once.
- The playback bar floats under the board: play and pause, the cursor buttons, "Pause
  after rounds" (stop before every new
  round), the speed (1×, 2×, 4×), and "N responses behind · Go live", which jumps to the
  live game.
- The stream keeps running while the playback is paused, and the header says "Catching
  up" until the playback reaches the live end.
- The board renders at most about 30 times a second while answers are written, the
  transcript and the player columns only render again when what they show changes, and
  the cards are only measured while the ballots show, which keeps a debrief with
  every player writing at once smooth.
- "Next response" (play until the next answer is in, then pause) was dropped, since it
  was easy to confuse with stepping to the next event.
- The cursor moves over the engine events. The buttons next to play step one event back
  or forward and jump to the previous or next phase, and the arrow keys do the same
  (left and right, with shift for phases). Stepping pauses the playback and rebuilds the
  board up to the cursor, with no answer being written, since partial answers are only
  shown while playing. Play continues from the cursor at the chosen speed, and the badge
  "N events ahead · Go live" shows how far the cursor is behind the stream. The tab must
  stay open until the game finishes, since it holds the SSE connection.

### Export and import

- **Export**: the Export button of the board header downloads `{config, events,
  exported_at, version}` as JSON. The file holds every private field of the game, since
  the audience and god modes are only a way of looking at it.
- **Import**: the setup view has an "Import a game" button that reads such a file
  (`lib/gameExport.ts` checks the version and that the events are complete and in `seq`
  order) and loads it into the same board in playback mode, without a backend game, shown
  as a replay from the start. Useful as a demo fallback when live APIs fail.

### Debrief panel

After `game_finished` has played, the board shows below the table, per player, a card with
role, model, clues, statements, vote and guess, the in-the-moment private reasoning at
each turn and the after-the-fact reflection side by side, plus tokens and cost
(`lib/debrief.ts` builds it from the events).

## Testing

- API: FastAPI's `TestClient` against the app, with fake players in the game setup of
  `agent.py`: the catalog, ADK serving only the game app, and a game created as a
  session and streamed over `/run_sse` to the end. Streaming of model tokens is tested on
  the player with a fake model, and was checked against real models with `curl`.
- Frontend: Vitest with Testing Library and jsdom. The stream client is tested against a
  mocked `fetch`, and the functions in `lib/` (board state, partial answers, playback,
  export) directly, including that audience mode shows nothing private. The look is
  checked by hand, with a check list and screenshots in the PR of each UI work package.
