/** A JSON value, as far as its text has arrived. */
export type PartialJsonValue =
  | string
  | number
  | boolean
  | null
  | PartialJsonValue[]
  | { [key: string]: PartialJsonValue };

/** Thrown inside the parser when the text ends or breaks off. */
class EndOfInput extends Error {}

const ESCAPES: Record<string, string> = {
  '"': '"',
  "\\": "\\",
  "/": "/",
  b: "\b",
  f: "\f",
  n: "\n",
  r: "\r",
  t: "\t",
};

const LITERALS: Record<string, PartialJsonValue> = {
  true: true,
  false: false,
  null: null,
};

/**
 * A recursive descent parser that keeps what it parsed when the text stops early.
 *
 * Containers and strings that are cut off are returned as far as they go. A key without
 * its value, a cut-off number or literal and anything after a syntax error are left out.
 */
class PartialJsonParser {
  private readonly text: string;
  private index = 0;

  constructor(text: string) {
    this.text = text;
  }

  parse(): PartialJsonValue | undefined {
    const start = this.text.indexOf("{");
    const arrayStart = this.text.indexOf("[");
    const first = [start, arrayStart].filter((index) => index >= 0);

    if (first.length === 0) {
      return undefined;
    }

    this.index = Math.min(...first);
    const result: { value?: PartialJsonValue } = {};

    try {
      this.value(result);
    } catch (error) {
      if (!(error instanceof EndOfInput)) {
        throw error;
      }
    }

    return result.value;
  }

  /** Parse the next value into `slot.value`, filling containers as they grow. */
  private value(slot: { value?: PartialJsonValue }): void {
    this.skipSpace();
    const char = this.peek();

    if (char === "{") {
      const object: Record<string, PartialJsonValue> = {};
      slot.value = object;
      this.object(object);
    } else if (char === "[") {
      const array: PartialJsonValue[] = [];
      slot.value = array;
      this.array(array);
    } else if (char === '"') {
      this.string(slot);
    } else if (char === "-" || (char >= "0" && char <= "9")) {
      slot.value = this.number();
    } else {
      slot.value = this.literal();
    }
  }

  private object(object: Record<string, PartialJsonValue>): void {
    this.index += 1;

    for (;;) {
      this.skipSpace();

      if (this.peek() === "}") {
        this.index += 1;
        return;
      }

      const key: { value?: PartialJsonValue } = {};
      this.string(key, { complete: true });
      this.skipSpace();
      this.expect(":");
      const entry: { value?: PartialJsonValue } = {};

      try {
        this.value(entry);
      } finally {
        if (entry.value !== undefined) {
          object[typeof key.value === "string" ? key.value : ""] = entry.value;
        }
      }

      this.skipSpace();

      if (this.peek() === ",") {
        this.index += 1;
      } else {
        this.expect("}");
        return;
      }
    }
  }

  private array(array: PartialJsonValue[]): void {
    this.index += 1;

    for (;;) {
      this.skipSpace();

      if (this.peek() === "]") {
        this.index += 1;
        return;
      }

      const item: { value?: PartialJsonValue } = {};

      try {
        this.value(item);
      } finally {
        if (item.value !== undefined) {
          array.push(item.value);
        }
      }

      this.skipSpace();

      if (this.peek() === ",") {
        this.index += 1;
      } else {
        this.expect("]");
        return;
      }
    }
  }

  /** Parse a string into `slot.value`, which holds the text so far if it is cut off. */
  private string(slot: { value?: PartialJsonValue }, { complete = false } = {}): void {
    this.expect('"');
    let text = "";

    for (;;) {
      if (!complete) {
        slot.value = text;
      }

      const char = this.peek();
      this.index += 1;

      if (char === '"') {
        slot.value = text;
        return;
      }

      if (char !== "\\") {
        text += char;
        continue;
      }

      const escape = this.peek();
      this.index += 1;

      if (escape === "u") {
        const hex = this.text.slice(this.index, this.index + 4);

        if (!/^[0-9a-fA-F]{4}$/.test(hex)) {
          throw new EndOfInput();
        }

        this.index += 4;
        text += String.fromCharCode(Number.parseInt(hex, 16));
      } else {
        text += ESCAPES[escape] ?? escape;
      }
    }
  }

  private number(): number {
    const match = /^-?\d+(\.\d+)?([eE][+-]?\d+)?/.exec(this.text.slice(this.index));

    // A number at the end of the text may still grow, so it waits for what follows.
    if (match === null || this.index + match[0].length >= this.text.length) {
      throw new EndOfInput();
    }

    this.index += match[0].length;

    return Number(match[0]);
  }

  private literal(): PartialJsonValue {
    for (const [word, value] of Object.entries(LITERALS)) {
      if (this.text.startsWith(word, this.index)) {
        this.index += word.length;
        return value;
      }
    }

    throw new EndOfInput();
  }

  private expect(char: string): void {
    if (this.peek() !== char) {
      throw new EndOfInput();
    }

    this.index += 1;
  }

  /** The next character, ending the parse when there is none. */
  private peek(): string {
    const char = this.text[this.index];

    if (char === undefined) {
      throw new EndOfInput();
    }

    return char;
  }

  private skipSpace(): void {
    while (/\s/.test(this.text[this.index] ?? "")) {
      this.index += 1;
    }
  }
}

/**
 * Parse the start of a JSON text, as a model streams it.
 *
 * Text before the first brace or bracket, such as a Markdown code fence, is skipped.
 * Returns `undefined` when no value has started yet.
 */
export function parsePartialJson(text: string): PartialJsonValue | undefined {
  return new PartialJsonParser(text).parse();
}

/** The string fields of the JSON object a text starts, as far as they have arrived. */
export function partialStringFields(text: string): Record<string, string> {
  const value = parsePartialJson(text);

  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}
