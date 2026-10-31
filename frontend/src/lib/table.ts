import type { GameEvent, GamePhase } from "@/api/types";
import type { BoardView } from "@/lib/boardView";

/** A step of the phase indicator. */
export interface PhaseStep {
  phase: GamePhase;
  label: string;
  /** `skipped` for a step the game went past without playing it. */
  state: "done" | "skipped" | "current" | "next";
}

/** The phases the indicator shows, each with the phases it stands for. */
export const PHASE_STEPS: { phase: GamePhase; label: string; covers: GamePhase[] }[] = [
  { phase: "clue", label: "Clues", covers: ["setup", "clue"] },
  { phase: "discussion", label: "Discussion", covers: ["discussion"] },
  { phase: "vote", label: "Vote", covers: ["vote", "resolution"] },
  { phase: "guess", label: "Guess", covers: ["guess"] },
  { phase: "outcome", label: "Reveal", covers: ["outcome"] },
  { phase: "debrief", label: "Debrief", covers: ["debrief", "done"] },
];

/**
 * The steps of the phase indicator at a phase.
 *
 * A game that ended early, when the word was said, jumps from its phase to the reveal.
 * When `finished` is set every step is past. A step that is past is done when one of
 * its phases is in `played`, the phases that started, and skipped when none is, for
 * example the vote and the guess of a game that ended in the discussion. Without
 * `played` every step that is past is done.
 */
export function phaseSteps({
  phase,
  finished = false,
  played,
}: {
  phase: GamePhase | null;
  finished?: boolean;
  played?: GamePhase[];
}): PhaseStep[] {
  const current = PHASE_STEPS.findIndex(
    (step) => phase !== null && step.covers.includes(phase),
  );

  return PHASE_STEPS.map(({ phase: stepPhase, label, covers }, index) => {
    let state: PhaseStep["state"] = "next";

    if (finished || (current >= 0 && index < current)) {
      const skipped =
        played !== undefined && !covers.some((covered) => played.includes(covered));
      state = skipped ? "skipped" : "done";
    } else if (index === current) {
      state = "current";
    }

    return { phase: stepPhase, label, state };
  });
}

/** The phases that started in a game, in the order they started. */
export function playedPhases(events: GameEvent[]): GamePhase[] {
  return events.flatMap((event) => (event.type === "phase_started" ? [event.phase] : []));
}

/**
 * The number of events up to the end of a step of the phase indicator, or `null` while
 * the step has not ended.
 *
 * A step ends when a phase it does not stand for starts after its last phase, or when
 * the game is over. Seeking to the returned count shows the board just before the next
 * phase, with everything of the step on it.
 */
export function phaseEnd(events: GameEvent[], step: GamePhase): number | null {
  const covers = PHASE_STEPS.find((candidate) => candidate.phase === step)?.covers ?? [];
  const starts = events.flatMap((event, position) =>
    event.type === "phase_started" ? [{ phase: event.phase, position }] : [],
  );
  const last = starts.findLastIndex((start) => covers.includes(start.phase));

  if (last === -1) {
    return null;
  }

  const next = starts.slice(last + 1).find((start) => !covers.includes(start.phase));

  if (next !== undefined) {
    return next.position;
  }

  return events.some((event) => event.type === "game_finished") ? events.length : null;
}

const PHASE_NAMES: Record<GamePhase, string> = {
  setup: "Setting up",
  clue: "Clue round",
  discussion: "Discussion round",
  vote: "Secret vote",
  resolution: "Vote reveal",
  guess: "The guess",
  outcome: "The reveal",
  debrief: "Debrief",
  done: "Game over",
  aborted: "Aborted",
};

/** The name of a phase as the table shows it, with its round when it has rounds. */
export function phaseTitle(phase: GamePhase | null, round: number | null): string {
  if (phase === null) {
    return "Shuffling seats";
  }

  return round === null ? PHASE_NAMES[phase] : `${PHASE_NAMES[phase]} ${round}`;
}

/** Format a cost in USD, with more digits for the small amounts a game costs. */
export function formatCost(costUsd: number): string {
  if (costUsd < 0.01) {
    return `$${costUsd.toFixed(4)}`;
  }

  return costUsd < 1 ? `$${costUsd.toFixed(3)}` : `$${costUsd.toFixed(2)}`;
}

/** Format a token count compactly, for example `12.3k`. */
export function formatTokens(tokens: number): string {
  if (tokens < 1000) {
    return String(tokens);
  }

  return tokens < 1_000_000
    ? `${(tokens / 1000).toFixed(1)}k`
    : `${(tokens / 1_000_000).toFixed(2)}M`;
}

/** A box on the board, in pixels from the top left of the table. */
export interface BoardRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The flight of a ballot: the points it passes, start, top of the arc and landing. */
export interface BallotFlight {
  x: [number, number, number];
  y: [number, number, number];
}

/**
 * The flight of a ballot from the voter's card to the target's card, as keyframes.
 *
 * It leaves from the middle of the voter's card and lands on the middle of the target's,
 * arcing above both cards by `lift` pixels plus a share of the distance, so a long throw
 * flies higher than a short one.
 */
export function ballotFlight({
  from,
  to,
  lift = 48,
}: {
  from: BoardRect;
  to: BoardRect;
  lift?: number;
}): BallotFlight {
  const start = { x: from.x + from.width / 2, y: from.y + from.height / 2 };
  const end = { x: to.x + to.width / 2, y: to.y + to.height / 2 };
  const distance = Math.hypot(end.x - start.x, end.y - start.y);
  const top = Math.min(from.y, to.y) - lift - distance * 0.12;
  const round = (value: number) => Math.round(value);

  return {
    x: [round(start.x), round((start.x + end.x) / 2), round(end.x)],
    y: [round(start.y), round(top), round(end.y)],
  };
}

/** How long a ballot flies from the voter to the target, in seconds. */
export const BALLOT_FLIGHT_SECONDS = 0.9;

/** The pause between two ballots of a reveal, in seconds. */
export const BALLOT_STAGGER_SECONDS = 0.5;

/** The phases in which the votes are shown as ballots on the seats. */
const BALLOT_PHASES = new Set<GamePhase>(["vote", "resolution", "guess", "outcome"]);

/** A vote as a ballot that flies from the voter's card and lands on the target's. */
export interface Ballot {
  voter: number;
  target: number;
  /** The name of the voter, written on the ballot. */
  name: string;
  revealed: boolean;
  /** When the ballot leaves the voter, in seconds after it appears. */
  delay: number;
}

/**
 * The ballots of the votes on the board, from the vote to the outcome.
 *
 * Revealed ballots leave one after another, so the reveal reads vote by vote. Secret
 * votes in god mode come in one by one as they are cast, so each leaves at once.
 * Abstentions have no ballot.
 */
export function boardBallots(view: BoardView): Ballot[] {
  if (view.votes === null || view.phase === null || !BALLOT_PHASES.has(view.phase)) {
    return [];
  }

  const { revealed, votes } = view.votes;
  const names = new Map(view.seats.map((seat) => [seat.seat, seat.name]));

  return votes
    .flatMap(({ voter, target }) => (target === null ? [] : [{ voter, target }]))
    .map(({ voter, target }, order) => ({
      voter,
      target,
      name: names.get(voter) ?? `Seat ${voter}`,
      revealed,
      delay: revealed ? order * BALLOT_STAGGER_SECONDS : 0,
    }));
}
