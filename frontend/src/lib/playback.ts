import type { PartialAnswer } from "@/api/gameStream";
import type { GameEvent, GameEventType } from "@/api/types";
import { type BoardState, boardReducer, INITIAL_BOARD } from "@/lib/board";

/** One thing the stream sent: an engine event, or a seat's answer as far as it grew. */
export type TimelineItem =
  { kind: "event"; event: GameEvent } | { kind: "answer"; answer: PartialAnswer };

/** An item of the timeline, with how it plays at normal speed. */
interface TimedItem {
  item: TimelineItem;
  /** How long the item plays at normal speed, in milliseconds. */
  duration: number;
  /** For an answer, the length of its text that was already shown before it. */
  shownBefore: number;
}

/** How fast answers are written out at normal speed. */
export const CHARACTERS_PER_SECOND = 60;

/** How much playback speeds up at most to catch up with a backlog. */
export const MAX_CATCH_UP = 5;

/** The backlog, in milliseconds at normal speed, that playback keeps without speeding up. */
export const CATCH_UP_BACKLOG = 8000;

/** The pause after each engine event, in milliseconds at normal speed, to take it in. */
const EVENT_PAUSES: Partial<Record<GameEventType, number>> = {
  game_started: 500,
  phase_started: 1200,
  turn_started: 250,
  clue_given: 1400,
  vote_cast: 300,
  guess_made: 2500,
  secret_word_said: 2000,
  outcome: 3500,
  reflection: 600,
};

/** The engine events that end a seat's turn with its answer: one response each. */
const RESPONSE_TYPES = new Set<GameEventType>([
  "clue_given",
  "statement_made",
  "vote_cast",
  "guess_made",
  "secret_word_said",
  "reflection",
]);

/** How long an engine event stays before the next item plays, at normal speed. */
export function eventPause(event: GameEvent): number {
  switch (event.type) {
    case "statement_made": {
      const words = event.statement.split(/\s+/).filter(Boolean).length;

      return Math.min(1000 + words * 120, 5000);
    }
    case "votes_revealed":
      return 1500 + event.votes.length * 600;
    default:
      return EVENT_PAUSES[event.type] ?? 0;
  }
}

/** Whether an item starts a new round or phase, after which a round is over. */
function startsRound(item: TimelineItem): boolean {
  return item.kind === "event" && item.event.type === "phase_started";
}

/** Whether an item is a seat's response. */
function isResponse(item: TimelineItem): boolean {
  return item.kind === "event" && RESPONSE_TYPES.has(item.event.type);
}

/**
 * The stream of a game as it arrived, with how long each item plays.
 *
 * Answers take the time their new characters need at `CHARACTERS_PER_SECOND`, so a big
 * chunk is written out as smoothly as many small ones, and the model's thinking takes no
 * time. Engine events take the pause that lets the audience read them.
 *
 * Attributes:
 *   items: The items in the order they arrived.
 */
export class GameTimeline {
  readonly items: TimedItem[] = [];
  /** The last answer of each seat, to tell how much of a new one is new. */
  private readonly lastAnswers = new Map<number, PartialAnswer>();

  /** Add the next item of the stream. */
  push(item: TimelineItem): void {
    if (item.kind === "event") {
      this.items.push({ item, duration: eventPause(item.event), shownBefore: 0 });
      return;
    }

    const { answer } = item;
    const last = this.lastAnswers.get(answer.seat);
    const shownBefore = last?.path === answer.path ? last.text.length : 0;
    const added = Math.max(answer.text.length - shownBefore, 0);
    this.lastAnswers.set(answer.seat, answer);
    this.items.push({
      item,
      duration: (added / CHARACTERS_PER_SECOND) * 1000,
      shownBefore,
    });
  }

  /** The number of items. */
  get length(): number {
    return this.items.length;
  }
}

/** Why playback stopped by itself. */
export type PlaybackPause = "round" | "step" | null;

/**
 * Plays a game's timeline at a pace the audience can follow.
 *
 * The items before `index` have been played. The item at `index` plays once it has
 * `started`, which shows an engine event at once and writes an answer out over its
 * duration. Playback runs at `speed` and speeds up smoothly, up to `MAX_CATCH_UP`
 * times, while more than `CATCH_UP_BACKLOG` of the timeline waits, so it never shows a
 * whole backlog at once. It can stop before each new round and after the next response.
 *
 * Attributes:
 *   timeline: The timeline it plays.
 *   index: The position of the item that plays next or now.
 *   elapsed: How far the current item has played, in milliseconds at normal speed.
 *   started: Whether the current item has started.
 *   playing: Whether the clock runs.
 *   speed: How fast it plays, 1 for normal speed.
 *   pauseAfterRounds: Whether it stops before each new round.
 *   stepping: Whether it stops after the next response.
 *   pausedFor: Why it stopped by itself, if it did.
 */
export class GamePlayback {
  readonly timeline: GameTimeline;
  index = 0;
  elapsed = 0;
  started = false;
  playing = true;
  speed = 1;
  pauseAfterRounds = false;
  stepping = false;
  pausedFor: PlaybackPause = null;
  /** The board of the items played so far, without the answer being written. */
  private played: BoardState = INITIAL_BOARD;

  constructor(timeline: GameTimeline) {
    this.timeline = timeline;
  }

  /** Whether every item that arrived has played: the board shows the live game. */
  get atLive(): boolean {
    return this.index >= this.timeline.length;
  }

  /** The time the waiting items take at normal speed, in milliseconds. */
  get backlog(): number {
    let total = 0;

    for (let index = this.index; index < this.timeline.length; index += 1) {
      total += this.timeline.items[index]?.duration ?? 0;
    }

    return Math.max(total - (this.started ? this.elapsed : 0), 0);
  }

  /** The responses that arrived and have not played yet. */
  get responsesBehind(): number {
    return this.timeline.items.slice(this.index).filter((timed) => isResponse(timed.item))
      .length;
  }

  /** The speed at which playback runs now, with the catch up for the backlog. */
  get effectiveSpeed(): number {
    const catchUp = Math.min(Math.max(this.backlog / CATCH_UP_BACKLOG, 1), MAX_CATCH_UP);

    return this.speed * catchUp;
  }

  /** Run the clock, starting the item it stopped before. */
  play(): void {
    this.playing = true;
    this.stepping = false;
    this.resume();
  }

  /** Stop the clock. */
  pause(): void {
    this.playing = false;
  }

  /** Play until the next response has been shown, then stop. */
  step(): void {
    this.playing = true;
    this.stepping = true;
    this.resume();
  }

  /** Play everything that arrived at once and follow the live game from there. */
  goLive(): void {
    while (!this.atLive) {
      this.startCurrent();
      this.finishCurrent();
    }

    this.pausedFor = null;
    this.stepping = false;
    this.playing = true;
  }

  /**
   * Move the clock on by some real time.
   *
   * Returns whether anything changed on the board.
   */
  advance(milliseconds: number): boolean {
    if (!this.playing) {
      return false;
    }

    let budget = milliseconds * this.effectiveSpeed;
    let changed = false;

    while (!this.atLive) {
      if (!this.started) {
        const item = this.timeline.items[this.index]?.item;

        // The first round has no round before it to stop after.
        const firstRound = !this.played.events.some(
          (event) => event.type === "phase_started",
        );

        if (
          item !== undefined &&
          this.pauseAfterRounds &&
          startsRound(item) &&
          !firstRound
        ) {
          this.stopFor("round");
          return changed;
        }

        this.startCurrent();
      }

      const duration = this.timeline.items[this.index]?.duration ?? 0;

      if (this.elapsed + budget < duration) {
        this.elapsed += budget;
        return true;
      }

      budget -= duration - this.elapsed;
      const finished = this.timeline.items[this.index]?.item;
      this.finishCurrent();
      changed = true;

      if (this.stepping && finished !== undefined && isResponse(finished)) {
        this.stopFor("step");
        return changed;
      }
    }

    return changed;
  }

  /** The board as far as it has played, with the answer being written so far. */
  board(): BoardState {
    const current = this.timeline.items[this.index];

    if (!this.started || current?.item.kind !== "answer") {
      return this.played;
    }

    const { answer } = current.item;
    const added = answer.text.length - current.shownBefore;
    const progress =
      current.duration > 0 ? Math.min(this.elapsed / current.duration, 1) : 1;
    const shown = current.shownBefore + Math.floor(added * progress);

    return boardReducer(this.played, {
      type: "answer",
      answer: { ...answer, text: answer.text.slice(0, shown) },
    });
  }

  private resume(): void {
    this.pausedFor = null;

    // An item that playback stopped before starts now, without stopping again.
    if (!this.atLive && !this.started) {
      this.startCurrent();
    }
  }

  private stopFor(reason: Exclude<PlaybackPause, null>): void {
    this.playing = false;
    this.stepping = false;
    this.pausedFor = reason;
  }

  private startCurrent(): void {
    const item = this.timeline.items[this.index]?.item;
    this.started = true;
    this.elapsed = 0;

    if (item?.kind === "event") {
      this.played = boardReducer(this.played, { type: "game_event", event: item.event });
    }
  }

  private finishCurrent(): void {
    const item = this.timeline.items[this.index]?.item;

    if (item?.kind === "answer") {
      this.played = boardReducer(this.played, { type: "answer", answer: item.answer });
    }

    this.index += 1;
    this.elapsed = 0;
    this.started = false;
  }
}
