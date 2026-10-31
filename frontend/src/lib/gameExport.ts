import type { GameEvent, GameRequest } from "@/api/types";
import { type BoardState, boardReducer, INITIAL_BOARD } from "@/lib/board";
import { GameTimeline } from "@/lib/playback";

/** The version of the export format, which changes when the file layout does. */
export const EXPORT_VERSION = 1;

/** A game as a file: what it was set up with and every engine event. */
export interface GameExport {
  config: GameRequest;
  events: GameEvent[];
  /** When the file was made, as an ISO timestamp. */
  exported_at: string;
  version: number;
}

/** Make the export of a game. */
export function buildGameExport({
  config,
  events,
  now = new Date(),
}: {
  config: GameRequest;
  events: GameEvent[];
  now?: Date;
}): GameExport {
  return { config, events, exported_at: now.toISOString(), version: EXPORT_VERSION };
}

/** The file name of an export, from the game it holds. */
export function exportFileName(events: GameEvent[]): string {
  const id = events[0]?.game_id ?? "game";

  return `imposter-${id}.json`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Read the text of an export file.
 *
 * Throws an error with a message for the user when the text is not an export of a game
 * that this version of the app can replay: events must start with `game_started` and
 * follow each other in `seq` order without gaps.
 */
export function parseGameExport(text: string): GameExport {
  let data: unknown;

  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("The file is not valid JSON.");
  }

  if (!isRecord(data) || !Array.isArray(data.events) || !isRecord(data.config)) {
    throw new Error("The file is not an export of an Imposter game.");
  }

  if (data.version !== EXPORT_VERSION) {
    throw new Error(
      `The export has version ${String(data.version)}, expected ${EXPORT_VERSION}.`,
    );
  }

  const events = data.events as unknown[];
  const valid = events.every(
    (event, position) =>
      isRecord(event) && typeof event.type === "string" && event.seq === position,
  );

  if (!valid || (events[0] as GameEvent | undefined)?.type !== "game_started") {
    throw new Error("The events of the file are not a complete game.");
  }

  return {
    config: data.config as unknown as GameRequest,
    events: events as GameEvent[],
    exported_at: typeof data.exported_at === "string" ? data.exported_at : "",
    version: EXPORT_VERSION,
  };
}

/** The timeline that replays events without a stream, with each event one item. */
export function timelineOfEvents(events: GameEvent[]): GameTimeline {
  const timeline = new GameTimeline();

  for (const event of events) {
    timeline.push({ kind: "event", event });
  }

  return timeline;
}

/** The board of events that were read from a file: the game is over, as it ended. */
export function boardOfEvents(events: GameEvent[]): BoardState {
  let board: BoardState = { ...INITIAL_BOARD, gameId: events[0]?.game_id ?? null };

  for (const event of events) {
    board = boardReducer(board, { type: "game_event", event });
  }

  return boardReducer(board, { type: "ended", stopped: false });
}

/** Offer text as a file download in the browser. */
export function downloadJson({ name, text }: { name: string; text: string }): void {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
