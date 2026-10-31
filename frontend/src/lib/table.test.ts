import { describe, expect, it } from "vitest";

import { buildBoardView } from "@/lib/boardView";
import {
  BALLOT_STAGGER_SECONDS,
  ballotFlight,
  boardBallots,
  formatCost,
  formatTokens,
  phaseEnd,
  phaseSteps,
  phaseTitle,
  playedPhases,
} from "@/lib/table";
import { clueGiven, gameFinished, phaseStarted, wholeGame } from "@/test/fixtures";

describe("phaseSteps", () => {
  it("marks the steps before the current phase as done", () => {
    expect(phaseSteps({ phase: "resolution" }).map((step) => step.state)).toEqual([
      "done",
      "done",
      "current",
      "next",
      "next",
      "next",
    ]);
  });

  it("marks every step done when the game finished", () => {
    expect(
      phaseSteps({ phase: "done", finished: true }).every(
        (step) => step.state === "done",
      ),
    ).toBe(true);
  });
});

describe("phaseSteps with the played phases", () => {
  it("marks the steps a game went past without playing them as skipped", () => {
    const played = playedPhases([
      phaseStarted(0, "clue", 1),
      phaseStarted(1, "discussion", 1),
      phaseStarted(2, "outcome"),
    ]);

    expect(phaseSteps({ phase: "outcome", played }).map((step) => step.state)).toEqual([
      "done",
      "done",
      "skipped",
      "skipped",
      "current",
      "next",
    ]);
  });

  it("does not skip the steps still to come", () => {
    const played = playedPhases([phaseStarted(0, "clue", 1)]);

    expect(phaseSteps({ phase: "clue", played }).map((step) => step.state)).toEqual([
      "current",
      "next",
      "next",
      "next",
      "next",
      "next",
    ]);
  });
});

describe("formatting", () => {
  it("names phases with their round", () => {
    expect(phaseTitle("clue", 2)).toBe("Clue round 2");
    expect(phaseTitle("vote", null)).toBe("Secret vote");
    expect(phaseTitle(null, null)).toBe("Shuffling seats");
  });

  it("formats cost and tokens compactly", () => {
    expect(formatCost(0.00042)).toBe("$0.0004");
    expect(formatCost(0.01234)).toBe("$0.012");
    expect(formatCost(2.5)).toBe("$2.50");
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(12_345)).toBe("12.3k");
  });
});

describe("phaseEnd", () => {
  const game = wholeGame();

  it("ends a step just before the next phase starts", () => {
    expect(phaseEnd(game, "clue")).toBe(8);
    expect(phaseEnd(game, "vote")).toBe(16);
  });

  it("does not end a step that is still running or has not started", () => {
    expect(phaseEnd(game, "guess")).toBeNull();
    expect(phaseEnd(game, "debrief")).toBeNull();
  });

  it("ends the last step when the game finished", () => {
    const finished = [...game, phaseStarted(19, "debrief"), gameFinished(20)];

    expect(phaseEnd(finished, "debrief")).toBe(finished.length);
  });

  it("ends a step after its last round", () => {
    const rounds = [
      phaseStarted(0, "clue", 1),
      clueGiven(1, 0, "beacon"),
      phaseStarted(2, "clue", 2),
      clueGiven(3, 0, "coast"),
      phaseStarted(4, "vote"),
    ];

    expect(phaseEnd(rounds, "clue")).toBe(4);
  });
});

describe("ballotFlight", () => {
  it("flies from the voter's card to the target's card, arcing above both", () => {
    const flight = ballotFlight({
      from: { x: 0, y: 100, width: 100, height: 100 },
      to: { x: 200, y: 100, width: 100, height: 100 },
    });

    expect(flight.x).toEqual([50, 150, 250]);
    expect(flight.y).toEqual([150, 28, 150]);
  });
});

describe("boardBallots", () => {
  const game = wholeGame();
  const revealedAt = game.findIndex((event) => event.type === "votes_revealed") + 1;

  function ballotsAt(count: number, mode: "audience" | "god") {
    return boardBallots(
      buildBoardView({
        events: game.slice(0, count),
        answers: {},
        mode,
        running: true,
        prices: {},
      }),
    );
  }

  it("throws the revealed ballots one after another, with the voter's name", () => {
    const ballots = ballotsAt(revealedAt, "audience");

    expect(ballots.map(({ voter, target }) => [voter, target])).toEqual([
      [0, 1],
      [1, 2],
      [2, 1],
    ]);
    expect(ballots.every((ballot) => ballot.revealed)).toBe(true);
    expect(ballots.map((ballot) => ballot.delay)).toEqual([
      0,
      BALLOT_STAGGER_SECONDS,
      2 * BALLOT_STAGGER_SECONDS,
    ]);
    expect(ballots[0]?.name).not.toBe("");
  });

  it("throws secret votes in god mode at once, and none in audience mode", () => {
    const secret = ballotsAt(revealedAt - 1, "god");

    expect(secret).toHaveLength(3);
    expect(secret.every((ballot) => !ballot.revealed && ballot.delay === 0)).toBe(true);
    expect(ballotsAt(revealedAt - 1, "audience")).toEqual([]);
  });

  it("has no ballots before the vote", () => {
    expect(ballotsAt(8, "god")).toEqual([]);
  });
});
