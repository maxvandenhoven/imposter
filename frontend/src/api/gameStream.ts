import { checkResponse, requestJson } from "@/api/http";
import { ServerSentEventParser } from "@/api/sse";
import type { AdkEvent, GameEvent, GameRequest } from "@/api/types";

/** The ADK app that plays the game. */
export const APP_NAME = "imposter";

/** The ADK user of every game session. The server reads the IAP identity from the request. */
export const USER_ID = "local";

/** The session state key of the `GameRequest`. */
export const REQUEST_STATE_KEY = "game:request";

/** The `customMetadata` key of the engine event that an ADK event carries. */
export const GAME_EVENT_METADATA_KEY = "game_event";

/** The author of the game workflow's events. */
export const GAME_RUNNER_AUTHOR = "game_runner";

/** The author of a player's model events: `player_{seat}_{phase}`. */
const PLAYER_AUTHOR = /^player_(\d+)_([a-z]+)$/;

/** The answer a seat is writing, as far as it has streamed. */
export interface PartialAnswer {
  /** The seat that writes the answer. */
  seat: number;
  /** The phase of the turn, from the author of the events. */
  phase: string;
  /** The node path of the attempt, which changes when the turn is tried again. */
  path: string;
  /** The answer text so far, the JSON answer of the turn. */
  text: string;
  /** The model's native thinking so far, kept apart from the answer. */
  thought: string;
}

/** What a game stream reports while it runs. */
export interface GameStreamHandlers {
  /** The session of the game was created, its id is the game id. */
  onSession?: (sessionId: string) => void;
  /** The next engine event, in `seq` order without gaps. */
  onGameEvent: (event: GameEvent) => void;
  /** A seat's answer grew, or started over with a new attempt. */
  onAnswer: (answer: PartialAnswer) => void;
  /** The run failed, the stream ends after this. */
  onError: (message: string) => void;
}

/** The last line ADK sends when a run fails, which is not an event. */
interface RunErrorLine {
  error: string;
}

function isRunErrorLine(data: unknown): data is RunErrorLine {
  return (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof data.error === "string"
  );
}

/**
 * Sorts the events of a game stream into engine events, partial answers and errors.
 *
 * Engine events are passed on in `seq` order: one that arrives early waits for the ones
 * before it, and a repeated one is dropped. Partial answers are kept per seat and start
 * over when a new node path appears, which is a new attempt of the turn. A failed run
 * sends an `errorCode` event from the game runner and then an error line, which repeats
 * the error, so the error line is only reported when no error event came before it.
 * Error events of players are failed model attempts that the game handles itself: a
 * `player_error` engine event reports them.
 */
export class GameStreamSorter {
  private readonly handlers: GameStreamHandlers;
  /** The `seq` of the next engine event to pass on. */
  private nextSeq = 0;
  /** Engine events that arrived before an event with a lower `seq`. */
  private readonly early = new Map<number, GameEvent>();
  /** The answer each seat is writing. */
  private readonly answers = new Map<number, PartialAnswer>();
  /** Whether a run error was reported. */
  private failed = false;

  constructor(handlers: GameStreamHandlers) {
    this.handlers = handlers;
  }

  /** Sort the data of one line of the stream. */
  push(data: unknown): void {
    if (isRunErrorLine(data)) {
      if (!this.failed) {
        this.fail(data.error);
      }

      return;
    }

    const event = data as AdkEvent;
    const { author } = event;

    if (author === GAME_RUNNER_AUTHOR && event.errorCode) {
      this.fail(event.errorMessage ?? event.errorCode);
      return;
    }

    const gameEvent = event.customMetadata?.[GAME_EVENT_METADATA_KEY];

    if (gameEvent !== undefined) {
      this.pushGameEvent(gameEvent as GameEvent);
      return;
    }

    const player = PLAYER_AUTHOR.exec(author);

    if (event.partial === true && player !== null) {
      this.pushPartial(event, Number(player[1]), player[2] ?? "");
    }
  }

  private fail(message: string): void {
    this.failed = true;
    this.handlers.onError(message);
  }

  private pushGameEvent(event: GameEvent): void {
    if (event.seq < this.nextSeq) {
      return;
    }

    this.early.set(event.seq, event);

    for (
      let next = this.early.get(this.nextSeq);
      next !== undefined;
      next = this.early.get(this.nextSeq)
    ) {
      this.early.delete(this.nextSeq);
      this.nextSeq += 1;
      this.handlers.onGameEvent(next);
    }
  }

  private pushPartial(event: AdkEvent, seat: number, phase: string): void {
    const path = event.nodeInfo?.path ?? "";
    const current = this.answers.get(seat);
    const answer =
      current?.path === path
        ? { ...current }
        : { seat, phase, path, text: "", thought: "" };

    for (const part of event.content?.parts ?? []) {
      if (part.thought === true) {
        answer.thought += part.text ?? "";
      } else {
        answer.text += part.text ?? "";
      }
    }

    this.answers.set(seat, answer);
    this.handlers.onAnswer(answer);
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Create the game's session with the request in its state, returning the session id. */
export async function createGameSession(
  request: GameRequest,
  signal: AbortSignal,
): Promise<string> {
  const session = await requestJson<{ id: string }>(
    `/apps/${APP_NAME}/users/${USER_ID}/sessions`,
    { method: "POST", body: { state: { [REQUEST_STATE_KEY]: request } }, signal },
  );

  return session.id;
}

/** Read the lines of an SSE response and push their data to the sorter. */
async function readStream(response: Response, sorter: GameStreamSorter): Promise<void> {
  if (response.body === null) {
    return;
  }

  const parser = new ServerSentEventParser();
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();

  try {
    for (;;) {
      const { done, value } = await reader.read();

      if (done) {
        return;
      }

      for (const data of parser.push(value)) {
        sorter.push(JSON.parse(data));
      }
    }
  } finally {
    // Close the connection when reading stops early.
    await reader.cancel().catch(() => undefined);
  }
}

/**
 * Create a game and play it, passing its stream to the handlers until it ends.
 *
 * The game runs as long as the stream is open: aborting `signal` closes it, and the
 * server aborts the game. An abort resolves quietly. Every other failure, of the
 * requests or of the run, is passed to `onError`, so the returned promise never rejects.
 */
export async function playGame({
  request,
  signal,
  handlers,
}: {
  request: GameRequest;
  signal: AbortSignal;
  handlers: GameStreamHandlers;
}): Promise<void> {
  try {
    const sessionId = await createGameSession(request, signal);
    handlers.onSession?.(sessionId);
    const body = {
      app_name: APP_NAME,
      user_id: USER_ID,
      session_id: sessionId,
      new_message: { role: "user", parts: [{ text: "Play the game." }] },
      streaming: true,
    };
    const runRequest = new Request(new URL("/run_sse", window.location.origin), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
    });
    const response = await checkResponse(await globalThis.fetch(runRequest, { signal }));
    await readStream(response, new GameStreamSorter(handlers));
  } catch (error) {
    if (!signal.aborted && !isAbort(error)) {
      handlers.onError(errorText(error));
    }
  }
}
