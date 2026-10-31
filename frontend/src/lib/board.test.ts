import { describe, expect, it } from "vitest";

import type { GameEvent } from "@/api/types";
import { boardReducer, type BoardState, INITIAL_BOARD, thinkingSeats } from "@/lib/board";
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

  it("clears a seat's answer when its turn ends or a new turn starts", () => {
    const answer = { seat: 1, phase: "clue", path: "p@1", text: '{"clue"', thought: "" };
    const writing = boardReducer(boardWith([gameStarted(0)]), { type: "answer", answer });
    const answered = boardReducer(writing, {
      type: "game_event",
      event: clueGiven(1, 1, "beacon"),
    });
    const restarted = boardReducer(writing, {
      type: "game_event",
      event: turnStarted(1, 1),
    });

    expect(writing.answers[1]).toEqual(answer);
    expect(answered.answers[1]).toBeUndefined();
    expect(restarted.answers[1]).toBeUndefined();
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
