import { describe, expect, it } from "vitest";

import { buildDebrief } from "@/lib/debrief";
import { reflection, wholeGame } from "@/test/fixtures";

const PRICES = { "claude-haiku": { input: 0.1, output: 0.5 } };

describe("buildDebrief", () => {
  it("gives every player a card with role, model and turns", () => {
    const cards = buildDebrief({ events: wholeGame(), prices: PRICES });

    expect(cards.map((card) => [card.name, card.role, card.modelId])).toEqual([
      ["Alice", "civilian", "gemini-flash"],
      ["Bob", "imposter", "claude-haiku"],
      ["Charlie", "civilian", "gpt-oss"],
    ]);
    expect(cards[1]?.turns.map((turn) => [turn.kind, turn.text, turn.target])).toEqual([
      ["clue", "coast", null],
      ["vote", null, 2],
      ["guess", "harbour", null],
    ]);
  });

  it("keeps the reasoning of each turn", () => {
    const [alice] = buildDebrief({ events: wholeGame(), prices: PRICES });

    expect(alice?.turns[0]?.reasoning).not.toBe("");
  });

  it("adds the reflection of a seat", () => {
    const events = [...wholeGame(), reflection(19, 0, "I should have been clearer.")];
    const cards = buildDebrief({ events, prices: PRICES });

    expect(cards[0]?.reflection).toBe("I should have been clearer.");
    expect(cards[1]?.reflection).toBeNull();
  });

  it("sums the tokens of a seat and prices the ones with a known model", () => {
    const cards = buildDebrief({ events: wholeGame(), prices: PRICES });

    expect(cards[1]?.tokens).toBe(1_100_000);
    expect(cards[1]?.costUsd).toBeCloseTo(0.15);
    expect(cards[0]?.tokens).toBe(0);
  });

  it("is empty before the game started", () => {
    expect(buildDebrief({ events: [], prices: PRICES })).toEqual([]);
  });
});
