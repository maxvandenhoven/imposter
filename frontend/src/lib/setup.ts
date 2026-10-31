import type {
  CatalogModel,
  CatalogResponse,
  GameRequest,
  IdentityMode,
  WordMode,
} from "@/api/types";

/** The fewest seats of a game, as `MIN_PLAYERS` in `config.py`. */
export const MIN_PLAYERS = 3;

/** The most seats of a game, a cost guardrail, as `MAX_PLAYERS` in `config.py`. */
export const MAX_PLAYERS = 8;

/** The allowed clue rounds, as `GameConfig` checks them. */
export const CLUE_ROUNDS = { min: 1, max: 3 };

/** The allowed discussion rounds, as `GameConfig` checks them. */
export const DISCUSSION_ROUNDS = { min: 0, max: 3 };

/** The allowed temperature override, as `GameConfig` checks it. */
export const TEMPERATURE = { min: 0, max: 2 };

/** The category choice that lets the server pick a random category. */
export const ANY_CATEGORY = "";

/** One word of letters or digits with internal hyphens or apostrophes, as the server. */
const SINGLE_WORD = /^[\p{L}\p{N}]+(?:['-][\p{L}\p{N}]+)*$/u;

/** Characters the server strips from both ends of a typed word. */
const SURROUNDING_PUNCTUATION = /^[\s"'.,;:!?()[\]{}]+|[\s"'.,;:!?()[\]{}]+$/g;

/** The options of the setup screen, as the form holds them. */
export interface SetupForm {
  wordMode: WordMode;
  /** The typed word, used in `typed` mode only. */
  word: string;
  /** The category of a random or typed word, `ANY_CATEGORY` for none. */
  category: string;
  /** The catalog id of each seat's model, in seat order before shuffling. */
  seats: string[];
  identityMode: IdentityMode;
  publicCategory: boolean;
  imposterHint: boolean;
  modelClueCheck: boolean;
  imposterCount: number;
  clueRounds: number;
  discussionRounds: number;
  statementWordCap: number;
  reasoningWordCap: number;
  tokenBudget: number;
  /** The temperature override, `null` to use each model's own. */
  temperature: number | null;
}

/** The setup form with the defaults of `game-rules.md` and the catalog's lineup. */
export function defaultSetupForm(catalog: CatalogResponse): SetupForm {
  return {
    wordMode: "random",
    word: "",
    category: ANY_CATEGORY,
    seats: [...catalog.default_lineup],
    identityMode: "names",
    publicCategory: false,
    imposterHint: false,
    modelClueCheck: true,
    imposterCount: 1,
    clueRounds: 2,
    discussionRounds: 2,
    statementWordCap: 100,
    reasoningWordCap: 60,
    tokenBudget: 200_000,
    temperature: null,
  };
}

/** The largest number of imposters for a number of seats: fewer than half the others. */
export function maxImposters(playerCount: number): number {
  return Math.max(0, Math.floor((playerCount - 1) / 2));
}

/** Strip the punctuation and whitespace the server strips from a typed word. */
export function cleanWord(text: string): string {
  return text.replace(SURROUNDING_PUNCTUATION, "");
}

function isWholeNumberBetween(value: number, min: number, max: number): boolean {
  return Number.isInteger(value) && value >= min && value <= max;
}

/**
 * Check the options against the limits the server enforces, returning every problem.
 *
 * Invalid options only fail once the game's run starts, so the setup screen checks them
 * before Start. An empty list means the game can start.
 */
export function setupProblems(form: SetupForm): string[] {
  const problems: string[] = [];
  const players = form.seats.length;

  if (form.wordMode === "typed" && !SINGLE_WORD.test(cleanWord(form.word))) {
    problems.push("The secret word must be exactly one word.");
  }

  if (players < MIN_PLAYERS || players > MAX_PLAYERS) {
    problems.push(`A game needs ${MIN_PLAYERS} to ${MAX_PLAYERS} players.`);
  } else if (!isWholeNumberBetween(form.imposterCount, 1, maxImposters(players))) {
    problems.push(
      `${players} players allow 1 to ${maxImposters(players)} imposters, not ${form.imposterCount}.`,
    );
  }

  if (!isWholeNumberBetween(form.clueRounds, CLUE_ROUNDS.min, CLUE_ROUNDS.max)) {
    problems.push(`Clue rounds must be ${CLUE_ROUNDS.min} to ${CLUE_ROUNDS.max}.`);
  }

  if (
    !isWholeNumberBetween(
      form.discussionRounds,
      DISCUSSION_ROUNDS.min,
      DISCUSSION_ROUNDS.max,
    )
  ) {
    problems.push(
      `Discussion rounds must be ${DISCUSSION_ROUNDS.min} to ${DISCUSSION_ROUNDS.max}.`,
    );
  }

  const positive = [
    [form.statementWordCap, "The statement word cap"],
    [form.reasoningWordCap, "The reasoning word cap"],
    [form.tokenBudget, "The token budget"],
  ] as const;

  for (const [value, label] of positive) {
    if (!isWholeNumberBetween(value, 1, Number.MAX_SAFE_INTEGER)) {
      problems.push(`${label} must be a whole number of at least 1.`);
    }
  }

  const { temperature } = form;

  if (
    temperature !== null &&
    !(temperature >= TEMPERATURE.min && temperature <= TEMPERATURE.max)
  ) {
    problems.push(`The temperature must be ${TEMPERATURE.min} to ${TEMPERATURE.max}.`);
  }

  return problems;
}

/** Build the game request of a valid form, with the models' display names. */
export function gameRequest(form: SetupForm, models: CatalogModel[]): GameRequest {
  const names = new Map(models.map((model) => [model.id, model.display_name]));

  return {
    config: {
      players: form.seats.map((modelId) => ({
        model_id: modelId,
        model_display_name: names.get(modelId) ?? null,
        persona: null,
      })),
      imposter_count: form.imposterCount,
      identity_mode: form.identityMode,
      public_category: form.publicCategory,
      imposter_hint: form.imposterHint,
      model_clue_check: form.modelClueCheck,
      clue_rounds: form.clueRounds,
      discussion_rounds: form.discussionRounds,
      statement_word_cap: form.statementWordCap,
      reasoning_word_cap: form.reasoningWordCap,
      token_budget: form.tokenBudget,
      temperature: form.temperature,
      seed: null,
    },
    words: {
      mode: form.wordMode,
      word: form.wordMode === "typed" ? cleanWord(form.word) : null,
      category:
        form.wordMode === "generated" || form.category === ANY_CATEGORY
          ? null
          : form.category,
    },
  };
}

/**
 * Pick a model for each of `count` seats at random, as different as the catalog allows.
 *
 * `random` returns numbers in `[0, 1)`, like `Math.random`, which tests replace.
 */
export function randomLineup(
  modelIds: string[],
  count: number,
  random: () => number = Math.random,
): string[] {
  const lineup: string[] = [];
  let pool: string[] = [];

  while (lineup.length < count && modelIds.length > 0) {
    if (pool.length === 0) {
      pool = [...modelIds];
    }

    const [picked] = pool.splice(Math.floor(random() * pool.length), 1);

    if (picked !== undefined) {
      lineup.push(picked);
    }
  }

  return lineup;
}
