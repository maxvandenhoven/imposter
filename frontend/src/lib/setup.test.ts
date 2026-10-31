import { describe, expect, it } from "vitest";

import {
  ANY_CATEGORY,
  defaultSetupForm,
  gameRequest,
  maxImposters,
  randomLineup,
  type SetupForm,
  setupProblems,
  type SetupSeat,
} from "@/lib/setup";
import { CATALOG } from "@/test/fixtures";

function form(patch: Partial<SetupForm> = {}): SetupForm {
  return { ...defaultSetupForm(CATALOG), ...patch };
}

/** `count` seats of one model, the first `imposters` of them chosen as imposters. */
function seats(count: number, imposters = 0): SetupSeat[] {
  return Array.from({ length: count }, (_, index) => ({
    modelId: "gpt-oss",
    imposter: index < imposters,
  }));
}

describe("setupProblems", () => {
  it("accepts the defaults", () => {
    expect(setupProblems(form())).toEqual([]);
  });

  it.each([
    [{ seats: seats(2) }, "A game needs 3 to 8 players."],
    [{ seats: seats(9) }, "A game needs 3 to 8 players."],
    [
      { seats: seats(4, 2) },
      "2 players are chosen as imposters, but the game has only 1.",
    ],
    [{ imposterCount: 2 }, "4 players allow 1 to 1 imposters, not 2."],
    [{ imposterCount: 0 }, "4 players allow 1 to 1 imposters, not 0."],
    [{ clueRounds: 0 }, "Clue rounds must be 1 to 3."],
    [{ clueRounds: 4 }, "Clue rounds must be 1 to 3."],
    [{ discussionRounds: 4 }, "Discussion rounds must be 0 to 3."],
    [{ discussionRounds: 1.5 }, "Discussion rounds must be 0 to 3."],
    [
      { statementWordCap: 0 },
      "The statement word cap must be a whole number of at least 1.",
    ],
    [
      { reasoningWordCap: Number.NaN },
      "The reasoning word cap must be a whole number of at least 1.",
    ],
    [{ tokenBudget: -5 }, "The token budget must be a whole number of at least 1."],
    [{ temperature: 2.5 }, "The temperature must be 0 to 2."],
    [{ temperature: Number.NaN }, "The temperature must be 0 to 2."],
    [{ wordMode: "typed", word: "" }, "The secret word must be exactly one word."],
    [
      { wordMode: "typed", word: "light house" },
      "The secret word must be exactly one word.",
    ],
  ] as [Partial<SetupForm>, string][])("reports %o", (patch, problem) => {
    expect(setupProblems(form(patch))).toEqual([problem]);
  });

  it("accepts a typed word with surrounding punctuation and inner hyphens", () => {
    expect(
      setupProblems(form({ wordMode: "typed", word: ' "jack-o-lantern!" ' })),
    ).toEqual([]);
  });

  it("allows more imposters in larger games", () => {
    expect(maxImposters(7)).toBe(3);
    expect(setupProblems(form({ seats: seats(7, 2), imposterCount: 3 }))).toEqual([]);
  });
});

describe("gameRequest", () => {
  it("names the seats after their models and keeps the options", () => {
    const request = gameRequest(
      form({ clueRounds: 3, temperature: 0.5 }),
      CATALOG.models,
    );

    expect(request.config.players[0]).toEqual({
      model_id: "gemini-flash",
      model_display_name: "Gemini Flash",
      persona: null,
      imposter: false,
    });
    expect(request.config.clue_rounds).toBe(3);
    expect(request.config.temperature).toBe(0.5);
    expect(request.words).toEqual({ mode: "random", word: null, category: null });
  });

  it("sends the players chosen as imposters", () => {
    const request = gameRequest(form({ seats: seats(4, 1) }), CATALOG.models);

    expect(request.config.players.map((player) => player.imposter)).toEqual([
      true,
      false,
      false,
      false,
    ]);
  });

  it("sends the cleaned typed word with its category", () => {
    const request = gameRequest(
      form({ wordMode: "typed", word: " Beacon. ", category: "objects" }),
      CATALOG.models,
    );

    expect(request.words).toEqual({ mode: "typed", word: "Beacon", category: "objects" });
  });

  it("sends no word or category for a generated word", () => {
    const request = gameRequest(
      form({ wordMode: "generated", word: "left", category: "food" }),
      CATALOG.models,
    );

    expect(request.words).toEqual({ mode: "generated", word: null, category: null });
  });

  it("sends no category when any category will do", () => {
    const request = gameRequest(form({ category: ANY_CATEGORY }), CATALOG.models);

    expect(request.words.category).toBeNull();
  });
});

describe("randomLineup", () => {
  it("uses every model once before repeating one", () => {
    const lineup = randomLineup(["a", "b", "c"], 5, () => 0);

    expect(lineup).toEqual(["a", "b", "c", "a", "b"]);
  });

  it("gives no seats without models", () => {
    expect(randomLineup([], 3)).toEqual([]);
  });
});
