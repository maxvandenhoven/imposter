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
    expect(eventPause(statementMade(0, 0, "word ".repeat(300)))).toBe(6000);
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

  it("writes answers faster with a backlog, smoothly and up to a limit", () => {
    const characters = (milliseconds: number) =>
      "x".repeat((CHARACTERS_PER_SECOND * milliseconds) / 1000);
    const small = playbackOf([answer(characters(1000))]);
    const medium = playbackOf([answer(characters(CATCH_UP_BACKLOG * 1.5))]);
    const large = playbackOf([answer(characters(CATCH_UP_BACKLOG * 10))]);

    expect(small.typingSpeed).toBe(1);
    expect(medium.typingSpeed).toBeCloseTo(1.5);
    expect(large.typingSpeed).toBe(MAX_CATCH_UP);
  });

  it("keeps the pause after an event as long, also with a backlog", () => {
    const backlog = "x".repeat((CHARACTERS_PER_SECOND * CATCH_UP_BACKLOG * 10) / 1000);
    const playback = playbackOf([gameStarted(0), answer(backlog)]);
    const pause = eventPause(gameStarted(0));

    playback.advance(pause - 10);

    expect(playback.index).toBe(0);

    playback.advance(20);

    expect(playback.index).toBe(1);
  });

  it("counts the backlog down as items play", () => {
    const playback = playbackOf([gameStarted(0), turnStarted(1, 0)]);
    const total = eventPause(gameStarted(0)) + eventPause(turnStarted(1, 0));

    expect(playback.backlog).toBe(total);

    playback.advance(eventPause(gameStarted(0)));

    expect(playback.backlog).toBe(eventPause(turnStarted(1, 0)));
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

  it("jumps to the live game", () => {
    const playback = playbackOf([gameStarted(0), answer("abc"), turnStarted(1, 1)]);
    playback.pause();

    playback.goLive();

    expect(playback.atLive).toBe(true);
    expect(playback.board().events).toHaveLength(2);
    expect(playback.board().answers[0]?.text).toBe("abc");
  });

  it("shows the event that is playing only once when it jumps to the live game", () => {
    const playback = playbackOf([gameStarted(0), clueGiven(1, 0, "beacon")]);
    playback.advance(eventPause(gameStarted(0)) + 1);

    playback.goLive();

    expect(playback.board().events.map((event) => event.seq)).toEqual([0, 1]);
  });

  it("plays new items as soon as they arrive when it is live", () => {
    const playback = playbackOf([]);
    playback.advance(100);
    playback.timeline.push({ kind: "event", event: gameStarted(0) });

    playback.advance(1);

    expect(playback.board().events).toHaveLength(1);
  });

  describe("the cursor", () => {
    const game = (): GamePlayback => {
      const playback = playbackOf([
        gameStarted(0),
        phaseStarted(1, "clue", 1),
        turnStarted(2, 0),
        answer("be"),
        clueGiven(3, 0, "beacon"),
        phaseStarted(4, "clue", 2),
        turnStarted(5, 1),
        clueGiven(6, 1, "harbour"),
      ]);
      playback.pause();

      return playback;
    };

    const seqs = (playback: GamePlayback): number[] =>
      playback.board().events.map((event) => event.seq);

    it("steps forward and back one event at a time", () => {
      const playback = game();

      playback.stepForward();
      playback.stepForward();

      expect(seqs(playback)).toEqual([0, 1]);
      expect(playback.eventsAhead).toBe(5);

      playback.stepBack();

      expect(seqs(playback)).toEqual([0]);
      expect(playback.playing).toBe(false);
    });

    it("does not step before the start or past the end", () => {
      const playback = game();

      playback.stepBack();
      expect(seqs(playback)).toEqual([]);

      for (let step = 0; step < 20; step += 1) {
        playback.stepForward();
      }

      expect(playback.board().events).toHaveLength(7);
      expect(playback.atLive).toBe(true);
      expect(playback.eventsAhead).toBe(0);
    });

    it("shows no answer being written after a jump", () => {
      const playback = game();

      playback.seek(3);

      expect(playback.board().answers).toEqual({});
    });

    it("jumps to the start of the next and the previous phase", () => {
      const playback = game();

      playback.nextPhase();
      expect(seqs(playback)).toEqual([0, 1]);

      playback.nextPhase();
      expect(seqs(playback)).toEqual([0, 1, 2, 3, 4]);

      playback.previousPhase();
      expect(seqs(playback)).toEqual([0, 1]);

      playback.previousPhase();
      expect(seqs(playback)).toEqual([]);
    });

    it("goes to the start of the current phase before the one earlier", () => {
      const playback = game();
      playback.seek(4);

      playback.previousPhase();

      expect(seqs(playback)).toEqual([0, 1]);
    });

    it("plays on from a jump at the chosen speed", () => {
      const playback = game();
      playback.seek(2);

      playback.play();
      playback.advance(60_000);

      expect(playback.board().events).toHaveLength(7);
    });

    it("rebuilds the same board as playing to the same point", () => {
      const played = game();
      played.play();
      played.advance(8_000);
      const shown = played.eventsShown;
      const jumped = game();

      jumped.seek(shown);

      expect(jumped.board().events).toEqual(played.board().events);
    });
  });
});
