import { describe, expect, it } from "vitest";

import { parsePartialJson, partialStringFields } from "@/lib/partialJson";

describe("parsePartialJson", () => {
  it.each([
    ['{"clue": "beacon"}', { clue: "beacon" }],
    ['{"clue": "bea', { clue: "bea" }],
    [
      '{"clue": "beacon", "private_reasoning": "Ships',
      {
        clue: "beacon",
        private_reasoning: "Ships",
      },
    ],
    ['{"clue"', {}],
    ['{"clue": ', {}],
    ["", undefined],
    ['{"a": 1, "b": [true, null, 2.5', { a: 1, b: [true, null] }],
    ['{"a": 1, "b": [true, null, 2.5]', { a: 1, b: [true, null, 2.5] }],
    ['{"a": {"b": "c"}, "d": fal', { a: { b: "c" } }],
  ])("parses %j as far as it goes", (text, expected) => {
    expect(parsePartialJson(text)).toEqual(expected);
  });

  it("decodes escapes, also a cut-off one", () => {
    expect(parsePartialJson(String.raw`{"s": "say \"hi\"\né`)).toEqual({
      s: 'say "hi"\né',
    });
    expect(parsePartialJson('{"s": "caf\\u00e9!"}')).toEqual({ s: "café!" });
    expect(parsePartialJson(String.raw`{"s": "end\u00`)).toEqual({ s: "end" });
    expect(parsePartialJson('{"s": "end\\')).toEqual({ s: "end" });
  });

  it("skips text before the first brace, such as a code fence", () => {
    expect(parsePartialJson('```json\n{"statement": "I think')).toEqual({
      statement: "I think",
    });
  });

  it("returns what it has at a syntax error", () => {
    expect(parsePartialJson('{"clue": "x" oops')).toEqual({ clue: "x" });
  });
});

describe("partialStringFields", () => {
  it("keeps only the string fields of an object", () => {
    expect(partialStringFields('{"clue": "bea", "n": 3, "o": {}')).toEqual({
      clue: "bea",
    });
  });

  it("is empty for text that is not an object", () => {
    expect(partialStringFields('["a"')).toEqual({});
    expect(partialStringFields("thinking...")).toEqual({});
  });
});
