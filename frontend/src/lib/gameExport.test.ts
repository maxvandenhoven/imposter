import { describe, expect, it } from "vitest";

import type { GameRequest } from "@/api/types";
import {
  boardOfEvents,
  buildGameExport,
  EXPORT_VERSION,
  exportFileName,
  parseGameExport,
  timelineOfEvents,
} from "@/lib/gameExport";
import { GamePlayback } from "@/lib/playback";
import { gameFinished, wholeGame } from "@/test/fixtures";

const CONFIG = {
  config: { players: [] },
  words: { mode: "random" },
} as unknown as GameRequest;

describe("game export", () => {
  it("imports back to the same events and config", () => {
    const events = wholeGame();
    const text = JSON.stringify(
      buildGameExport({ config: CONFIG, events, now: new Date("2026-10-31T10:00:00Z") }),
    );

    const imported = parseGameExport(text);

    expect(imported.events).toEqual(events);
    expect(imported.config).toEqual(CONFIG);
    expect(imported.exported_at).toBe("2026-10-31T10:00:00.000Z");
    expect(imported.version).toBe(EXPORT_VERSION);
  });

  it("replays an import identically to the game", () => {
    const events = [...wholeGame(), gameFinished(19)];
    const imported = parseGameExport(
      JSON.stringify(buildGameExport({ config: CONFIG, events })),
    );
    const playback = new GamePlayback(timelineOfEvents(imported.events));

    playback.advance(10 * 60_000);

    expect(playback.atLive).toBe(true);
    expect(playback.board().events).toEqual(events);
    expect(boardOfEvents(imported.events).status).toBe("finished");
  });

  it("names the file after the game", () => {
    expect(exportFileName(wholeGame())).toBe("imposter-game-1.json");
  });

  it.each([
    ["not json", "{", "not valid JSON"],
    ["a list", "[]", "not an export"],
    [
      "another version",
      JSON.stringify({ version: 9, config: {}, events: [] }),
      "version 9",
    ],
    [
      "events with a gap",
      JSON.stringify({
        version: 1,
        config: {},
        events: [wholeGame()[0], wholeGame()[2]],
      }),
      "not a complete game",
    ],
    [
      "events without a start",
      JSON.stringify({ version: 1, config: {}, events: [wholeGame()[1]] }),
      "not a complete game",
    ],
  ])("rejects %s", (_name, text, message) => {
    expect(() => parseGameExport(text)).toThrow(message);
  });
});
