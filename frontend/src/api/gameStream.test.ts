import { describe, expect, it, vi } from "vitest";

import {
  type GameStreamHandlers,
  GameStreamSorter,
  type PartialAnswer,
  playGame,
} from "@/api/gameStream";
import type { GameEvent, GameRequest } from "@/api/types";
import { defaultSetupForm, gameRequest } from "@/lib/setup";
import { controlledEventStream, mockApi, serverSentEvents } from "@/test/api";
import {
  adkGameEvent,
  adkPartial,
  CATALOG,
  clueGiven,
  gameStarted,
  turnStarted,
} from "@/test/fixtures";

const SESSIONS_PATH = "POST /apps/imposter/users/local/sessions";

const REQUEST: GameRequest = gameRequest(defaultSetupForm(CATALOG), CATALOG.models);

/** Handlers that record what the stream reports. */
function recordingHandlers() {
  const events: GameEvent[] = [];
  const answers: PartialAnswer[] = [];
  const errors: string[] = [];
  const handlers: GameStreamHandlers = {
    onGameEvent: (event) => events.push(event),
    onAnswer: (answer) => answers.push(answer),
    onError: (message) => errors.push(message),
  };

  return { events, answers, errors, handlers };
}

/** Stream `lines` as the response of `/run_sse` and play a game to its end. */
async function playStream(lines: unknown[]) {
  const recorded = recordingHandlers();
  const requests = mockApi({
    [SESSIONS_PATH]: () => ({ body: { id: "session-1" } }),
    "POST /run_sse": () =>
      new Response(serverSentEvents(lines), {
        headers: { "Content-Type": "text/event-stream" },
      }),
  });

  await playGame({
    request: REQUEST,
    signal: new AbortController().signal,
    handlers: recorded.handlers,
  });

  return { ...recorded, requests };
}

describe("playGame", () => {
  it("creates the session with the request in its state and streams the run", async () => {
    const { requests } = await playStream([]);

    expect(requests[0]?.body).toEqual({ state: { "game:request": REQUEST } });
    expect(requests[1]?.body).toMatchObject({
      app_name: "imposter",
      user_id: "local",
      session_id: "session-1",
      streaming: true,
    });
  });

  it("passes the engine events on in seq order", async () => {
    const started = gameStarted(0);
    const turn = turnStarted(1, 0);
    const clue = clueGiven(2, 0, "beacon");

    const { events, errors } = await playStream([
      adkGameEvent(started),
      adkGameEvent(clue),
      adkGameEvent(turn),
      adkGameEvent(turn),
      { author: "game_runner", invocationId: "e-1", output: { route: "vote" } },
    ]);

    expect(events).toEqual([started, turn, clue]);
    expect(errors).toEqual([]);
  });

  it("builds the partial answer of each seat with thinking kept apart", async () => {
    const { answers } = await playStream([
      adkPartial({ seat: 0, text: "Hmm, ", thought: true }),
      adkPartial({ seat: 0, text: '{"clue": "bea' }),
      adkPartial({ seat: 1, phase: "vote", text: '{"tar' }),
      adkPartial({ seat: 0, text: 'con"}' }),
    ]);

    expect(answers.at(-1)).toMatchObject({
      seat: 0,
      phase: "clue",
      text: '{"clue": "beacon"}',
      thought: "Hmm, ",
    });
    expect(answers[2]).toMatchObject({ seat: 1, phase: "vote", text: '{"tar' });
  });

  it("starts an answer over when a new attempt of the turn appears", async () => {
    const { answers } = await playStream([
      adkPartial({ seat: 0, text: '{"clue": "light' }),
      adkPartial({ seat: 0, attempt: 2, text: '{"clue": "be' }),
      adkPartial({ seat: 0, attempt: 2, text: 'acon"}' }),
    ]);

    expect(answers.map((answer) => answer.text)).toEqual([
      '{"clue": "light',
      '{"clue": "be',
      '{"clue": "beacon"}',
    ]);
    expect(answers.at(-1)?.path).toMatch(/player_0_clue@2$/);
  });

  it("reports a failed run once, from its error event", async () => {
    const { errors } = await playStream([
      {
        author: "game_runner",
        invocationId: "e-1",
        errorCode: "ValidationError",
        errorMessage: "A game needs 3 players.",
      },
      { error: "ValidationError: A game needs 3 players.", error_details: {} },
    ]);

    expect(errors).toEqual(["A game needs 3 players."]);
  });

  it("reports the error line of a run that failed without an error event", async () => {
    const { errors } = await playStream([
      { error: "RuntimeError: Boom.", error_details: {} },
    ]);

    expect(errors).toEqual(["RuntimeError: Boom."]);
  });

  it("leaves the failed model attempts of players to the game", async () => {
    const { errors } = await playStream([
      {
        author: "player_0_clue",
        invocationId: "e-1",
        errorCode: "429",
        errorMessage: "Resource exhausted.",
      },
    ]);

    expect(errors).toEqual([]);
  });

  it("reports a failed request", async () => {
    const recorded = recordingHandlers();
    mockApi({ [SESSIONS_PATH]: () => ({ status: 500, body: { detail: "Broken." } }) });

    await playGame({
      request: REQUEST,
      signal: new AbortController().signal,
      handlers: recorded.handlers,
    });

    expect(recorded.errors).toEqual(["Broken."]);
  });

  it("closes the stream quietly when aborted", async () => {
    const recorded = recordingHandlers();
    const controller = new AbortController();
    let stream: ReturnType<typeof controlledEventStream> | undefined;
    const requests = mockApi({
      [SESSIONS_PATH]: () => ({ body: { id: "session-1" } }),
      "POST /run_sse": (request) => {
        stream = controlledEventStream(request.signal);
        return stream.response;
      },
    });

    const played = playGame({
      request: REQUEST,
      signal: controller.signal,
      handlers: recorded.handlers,
    });
    await vi.waitFor(() => {
      expect(stream).toBeDefined();
    });
    stream?.send(adkGameEvent(gameStarted(0)));
    await vi.waitFor(() => {
      expect(recorded.events).toHaveLength(1);
    });
    controller.abort();
    await played;

    expect(requests[1]?.signal?.aborted).toBe(true);
    expect(recorded.errors).toEqual([]);
  });
});

describe("GameStreamSorter", () => {
  it("passes an engine event that arrived early once the gap is filled", () => {
    const { events, handlers } = recordingHandlers();
    const sorter = new GameStreamSorter(handlers);

    sorter.push(adkGameEvent(turnStarted(1, 0)));
    expect(events).toEqual([]);
    sorter.push(adkGameEvent(gameStarted(0)));

    expect(events.map((event) => event.seq)).toEqual([0, 1]);
  });
});
