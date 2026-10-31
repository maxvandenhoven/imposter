import { describe, expect, it } from "vitest";

import {
  ANY_CATEGORY,
  defaultSetupForm,
  dragShift,
  dragTarget,
  gameRequest,
  maxImposters,
  moveSeat,
  randomImposters,
  randomLineup,
  removeSeat,
  type SetupForm,
  setupProblems,
  type SetupSeat,
} from "@/lib/setup";
import { CATALOG } from "@/test/fixtures";

function form(patch: Partial<SetupForm> = {}): SetupForm {
  return { ...defaultSetupForm(CATALOG, () => 0), ...patch };
}

/** `count` seats of one model, the first `imposters` of them chosen as imposters. */
function seats(count: number, imposters = 0): SetupSeat[] {
  return Array.from({ length: count }, (_, index) => ({
    id: index,
    modelId: "gpt-oss",
    imposter: index < imposters,
  }));
}

describe("setupProblems", () => {
  it("accepts the defaults", () => {
    expect(setupProblems(form())).toEqual([]);
  });

  it.each([
    [{ seats: seats(2, 1) }, "A game needs 3 to 8 players."],
    [{ seats: seats(9, 1) }, "A game needs 3 to 8 players."],
    [{ seats: seats(4, 2) }, "4 players allow at most 1 imposters, not 2."],
    [{ seats: seats(4) }, "Choose at least one imposter."],
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
    expect(setupProblems(form(patch)).map(({ message }) => message)).toEqual([problem]);
  });

  it("accepts a typed word with surrounding punctuation and inner hyphens", () => {
    expect(
      setupProblems(form({ wordMode: "typed", word: ' "jack-o-lantern!" ' })),
    ).toEqual([]);
  });

  it("puts each problem in the section of the setup where it is fixed", () => {
    const problems = setupProblems(
      form({ wordMode: "typed", word: "", seats: seats(4), clueRounds: 9 }),
    );

    expect(problems.map(({ section }) => section)).toEqual(["word", "players", "rules"]);
  });

  it("allows more imposters in larger games", () => {
    expect(maxImposters(7)).toBe(3);
    expect(setupProblems(form({ seats: seats(7, 3) }))).toEqual([]);
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
      imposter: true,
    });
    expect(request.config.imposter_count).toBe(1);
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

describe("imposter allocation", () => {
  it("puts one imposter on a random seat by default", () => {
    const { seats: lineup } = defaultSetupForm(CATALOG, () => 0.99);

    expect(lineup.map((seat) => seat.imposter)).toEqual([false, false, false, true]);
  });

  it("moves the imposters to random seats and keeps their number", () => {
    const moved = randomImposters(seats(7, 2), () => 0.99);

    expect(moved.map((seat) => seat.imposter)).toEqual([
      false,
      false,
      false,
      false,
      false,
      true,
      true,
    ]);
  });

  it("gives the role to another seat when the last imposter's seat is removed", () => {
    const rest = removeSeat(seats(4, 1), 0, () => 0);

    expect(rest.map((seat) => seat.imposter)).toEqual([true, false, false]);
    expect(removeSeat(seats(5, 2), 0).filter((seat) => seat.imposter)).toHaveLength(1);
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

describe("moveSeat", () => {
  it("moves a seat with its model and imposter mask", () => {
    const lineup = seats(4, 1).map((seat, index) => ({ ...seat, modelId: `m${index}` }));

    const moved = moveSeat({ seats: lineup, from: 0, to: 2 });

    expect(moved.map((seat) => seat.modelId)).toEqual(["m1", "m2", "m0", "m3"]);
    expect(moved[2]).toEqual({ id: 0, modelId: "m0", imposter: true });
  });

  it("leaves the seats as they are for an index out of range", () => {
    const lineup = seats(3, 1);

    expect(moveSeat({ seats: lineup, from: 0, to: 3 })).toBe(lineup);
    expect(moveSeat({ seats: lineup, from: 5, to: 0 })).toBe(lineup);
  });
});

describe("dragging a seat", () => {
  it("drops into the slot the drag reached, within the seats", () => {
    expect(dragTarget({ from: 0, offset: 70, step: 40, count: 4 })).toBe(2);
    expect(dragTarget({ from: 1, offset: -15, step: 40, count: 4 })).toBe(1);
    expect(dragTarget({ from: 3, offset: 400, step: 40, count: 4 })).toBe(3);
    expect(dragTarget({ from: 1, offset: -400, step: 40, count: 4 })).toBe(0);
  });

  it("moves the passed seats one row aside and leaves the others", () => {
    const shifts = (from: number, target: number) =>
      [0, 1, 2, 3].map((index) => dragShift({ index, from, target, step: 40 }));

    expect(shifts(0, 2)).toEqual([0, -40, -40, 0]);
    expect(shifts(3, 1)).toEqual([0, 40, 40, 0]);
    expect(shifts(2, 2)).toEqual([0, 0, 0, 0]);
  });
});
