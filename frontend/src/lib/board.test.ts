import { describe, expect, it } from "vitest";

import type { GameEvent } from "@/api/types";
import {
  boardReducer,
  type BoardState,
  describeEvent,
  INITIAL_BOARD,
  seatNames,
  thinkingSeats,
} from "@/lib/board";
import { clueGiven, gameStarted, turnStarted, voteCast } from "@/test/fixtures";

function boardWith(events: GameEvent[]): BoardState {
  return events.reduce(
    (board, event) => boardReducer(board, { type: "game_event", event }),
    INITIAL_BOARD,
  );
}

describe("boardReducer", () => {
  it("keeps the latest answer per seat", () => {
    const answer = { seat: 1, phase: "clue", path: "p@1", text: '{"clue"', thought: "" };
    const board = boardReducer(INITIAL_BOARD, { type: "answer", answer });

    expect(board.answers[1]).toEqual(answer);
  });

  it.each([
    [
      [
        gameStarted(0),
        { ...gameStarted(1), type: "game_finished", outcome: "imposter_wins" },
      ],
      false,
      "finished",
    ],
    [
      [gameStarted(0), { ...gameStarted(1), type: "game_aborted", reason: "Budget." }],
      false,
      "aborted",
    ],
    [[gameStarted(0)], true, "stopped"],
    [[gameStarted(0)], false, "failed"],
  ] as const)("ends a stream of %o, stopped %s, as %s", (events, stopped, status) => {
    const board = boardReducer(boardWith(events as unknown as GameEvent[]), {
      type: "ended",
      stopped,
    });

    expect(board.status).toBe(status);
  });
});

describe("thinkingSeats", () => {
  it("lists the seats whose turn started and has not ended", () => {
    const events = [
      gameStarted(0),
      turnStarted(1, 0),
      clueGiven(2, 0, "beacon"),
      turnStarted(3, 1),
      turnStarted(4, 2),
      voteCast(5, 2, 0),
    ];

    expect(thinkingSeats(events)).toEqual([1]);
  });
});

describe("describeEvent", () => {
  const names = seatNames([gameStarted(0)]);

  it("names the seats", () => {
    expect(describeEvent(clueGiven(1, 2, "beacon"), names)).toBe(
      'Charlie gives the clue "beacon".',
    );
    expect(describeEvent(clueGiven(1, 0, null), names)).toBe("Alice passes.");
  });

  it("keeps a vote secret until the votes are revealed", () => {
    expect(describeEvent(voteCast(1, 0, 1), names)).toBe("Alice has voted.");
  });
});
