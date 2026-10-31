import { describe, expect, it } from "vitest";

import type { PartialAnswer } from "@/api/gameStream";
import type { GameEvent } from "@/api/types";
import {
  CATCH_UP_BACKLOG,
  CHARACTERS_PER_SECOND,
  eventPause,
  GamePlayback,
  GameTimeline,
  MAX_CATCH_UP,
} from "@/lib/playback";
import {
  clueGiven,
  gameStarted,
  phaseStarted,
  statementMade,
  turnStarted,
} from "@/test/fixtures";

/** The milliseconds that `characters` of answer take at normal speed. */
function typing(characters: number): number {
  return (characters / CHARACTERS_PER_SECOND) * 1000;
}

function answer(text: string, path = "p0@1"): PartialAnswer {
  return { seat: 0, phase: "clue", path, text, thought: "" };
}

function playbackOf(items: (GameEvent | PartialAnswer)[]): GamePlayback {
  const timeline = new GameTimeline();

  for (const item of items) {
    timeline.push(
      "type" in item ? { kind: "event", event: item } : { kind: "answer", answer: item },
    );
  }

  return new GamePlayback(timeline);
}

describe("GameTimeline", () => {
  it("times answers by their new characters and events by their pause", () => {
    const playback = playbackOf([
      gameStarted(0),
      answer("0123456789"),
      answer("0123456789abcdefghij"),
      answer("0123", "p0@2"),
    ]);

    expect(playback.timeline.items.map((timed) => timed.duration)).toEqual([
      eventPause(gameStarted(0)),
      typing(10),
      typing(10),
      typing(4),
    ]);
  });

  it("gives longer statements longer to read, up to a cap", () => {
    expect(eventPause(statementMade(0, 0, "Short."))).toBeLessThan(
      eventPause(statementMade(0, 0, "word ".repeat(30))),
    );
    expect(eventPause(statementMade(0, 0, "word ".repeat(300)))).toBe(5000);
  });
});

describe("GamePlayback", () => {
  it("writes an answer out over its duration instead of at once", () => {
    const text = '{"clue": "beacon"}';
    const playback = playbackOf([answer(text)]);

    playback.advance(typing(text.length) / 2);

    expect(playback.board().answers[0]?.text).toBe(text.slice(0, text.length / 2));

    playback.advance(typing(text.length));

    expect(playback.board().answers[0]?.text).toBe(text);
    expect(playback.atLive).toBe(true);
  });

  it("shows an engine event at once and waits its pause before the next item", () => {
    const playback = playbackOf([gameStarted(0), turnStarted(1, 0)]);

    playback.advance(1);

    expect(playback.board().events).toHaveLength(1);

    playback.advance(eventPause(gameStarted(0)));

    expect(playback.board().events).toHaveLength(2);
  });

  it("does nothing while paused and resumes where it stopped", () => {
    const playback = playbackOf([gameStarted(0), turnStarted(1, 0)]);
    playback.pause();

    expect(playback.advance(10_000)).toBe(false);
    expect(playback.board().events).toHaveLength(0);

    playback.play();

    expect(playback.board().events).toHaveLength(1);
  });

  it("speeds up smoothly with a backlog, up to a limit", () => {
    const small = playbackOf([answer("x".repeat(10))]);
    const large = playbackOf([answer("x".repeat(CHARACTERS_PER_SECOND * 1000))]);
    const medium = playbackOf([
      answer("x".repeat((CHARACTERS_PER_SECOND * CATCH_UP_BACKLOG * 2) / 1000)),
    ]);

    expect(small.effectiveSpeed).toBe(1);
    expect(medium.effectiveSpeed).toBeCloseTo(2);
    expect(large.effectiveSpeed).toBe(MAX_CATCH_UP);
  });

  it("stops before each new round when asked, but not before the first", () => {
    const playback = playbackOf([
      gameStarted(0),
      phaseStarted(1, "clue", 1),
      clueGiven(2, 0, "beacon"),
      phaseStarted(3, "clue", 2),
      clueGiven(4, 0, "harbour"),
    ]);
    playback.pauseAfterRounds = true;

    playback.advance(60_000);

    expect(playback.pausedFor).toBe("round");
    expect(playback.board().events.map((event) => event.seq)).toEqual([0, 1, 2]);

    playback.play();
    playback.advance(60_000);

    expect(playback.board().events).toHaveLength(5);
  });

  it("steps to the end of the next response and stops there", () => {
    const playback = playbackOf([
      turnStarted(0, 0),
      clueGiven(1, 0, "beacon"),
      turnStarted(2, 1),
      clueGiven(3, 1, "harbour"),
    ]);
    playback.pause();

    playback.step();
    playback.advance(60_000);

    expect(playback.pausedFor).toBe("step");
    expect(playback.board().events).toHaveLength(2);
    expect(playback.responsesBehind).toBe(1);
  });

  it("jumps to the live game", () => {
    const playback = playbackOf([gameStarted(0), answer("abc"), turnStarted(1, 1)]);
    playback.pause();

    playback.goLive();

    expect(playback.atLive).toBe(true);
    expect(playback.board().events).toHaveLength(2);
    expect(playback.board().answers[0]?.text).toBe("abc");
  });

  it("plays new items as soon as they arrive when it is live", () => {
    const playback = playbackOf([]);
    playback.advance(100);
    playback.timeline.push({ kind: "event", event: gameStarted(0) });

    playback.advance(1);

    expect(playback.board().events).toHaveLength(1);
  });
});
