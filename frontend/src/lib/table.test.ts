import { describe, expect, it } from "vitest";

import {
  formatCost,
  formatTokens,
  phaseSteps,
  phaseTitle,
  seatCells,
  voteArrow,
} from "@/lib/table";

describe("seatCells", () => {
  it.each([3, 4, 5, 6, 7, 8])(
    "places %i seats in distinct cells around the middle",
    (n) => {
      const cells = seatCells(n);
      const keys = new Set(cells.map((cell) => `${cell.row},${cell.column}`));

      expect(cells).toHaveLength(n);
      expect(keys.size).toBe(n);
      expect(keys.has("2,2")).toBe(false);
    },
  );
});

describe("phaseSteps", () => {
  it("marks the steps before the current phase as done", () => {
    expect(phaseSteps("resolution").map((step) => step.state)).toEqual([
      "done",
      "done",
      "current",
      "next",
      "next",
      "next",
    ]);
  });

  it("marks every step done when the game finished", () => {
    expect(phaseSteps("done", true).every((step) => step.state === "done")).toBe(true);
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

describe("voteArrow", () => {
  it("runs from the edge of the voter to just before the edge of the target", () => {
    const arrow = voteArrow({
      from: { x: 0, y: 0, width: 100, height: 100 },
      to: { x: 300, y: 0, width: 100, height: 100 },
      bend: 0,
      gap: 10,
    });

    expect(arrow.path).toBe("M 100 50 Q 195 50 290 50");
    expect(arrow.tip).toEqual({ x: 290, y: 50, angle: 0 });
  });

  it("bends the two votes between the same seats to opposite sides", () => {
    const a = { x: 0, y: 0, width: 100, height: 100 };
    const b = { x: 300, y: 0, width: 100, height: 100 };

    expect(voteArrow({ from: a, to: b }).path).toBe("M 100 50 Q 197 14 294 50");
    expect(voteArrow({ from: b, to: a }).path).toBe("M 300 50 Q 203 86 106 50");
  });
});
