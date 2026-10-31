import type { GamePhase } from "@/api/types";

/** A cell of the 3 by 3 table grid, rows and columns counted from 1. */
export interface TableCell {
  row: number;
  column: number;
}

const TOP_LEFT = { row: 1, column: 1 };
const TOP = { row: 1, column: 2 };
const TOP_RIGHT = { row: 1, column: 3 };
const RIGHT = { row: 2, column: 3 };
const BOTTOM_RIGHT = { row: 3, column: 3 };
const BOTTOM = { row: 3, column: 2 };
const BOTTOM_LEFT = { row: 3, column: 1 };
const LEFT = { row: 2, column: 1 };

/** The cells around the table for each number of seats, clockwise from the top. */
const SEAT_CELLS: Record<number, TableCell[]> = {
  1: [TOP],
  2: [LEFT, RIGHT],
  3: [TOP, BOTTOM_RIGHT, BOTTOM_LEFT],
  4: [TOP, RIGHT, BOTTOM, LEFT],
  5: [TOP_LEFT, TOP_RIGHT, RIGHT, BOTTOM, LEFT],
  6: [TOP_LEFT, TOP_RIGHT, RIGHT, BOTTOM_RIGHT, BOTTOM_LEFT, LEFT],
  7: [TOP_LEFT, TOP, TOP_RIGHT, RIGHT, BOTTOM_RIGHT, BOTTOM_LEFT, LEFT],
  8: [TOP_LEFT, TOP, TOP_RIGHT, RIGHT, BOTTOM_RIGHT, BOTTOM, BOTTOM_LEFT, LEFT],
};

/**
 * Place the seats around the table, which takes the middle cell of a 3 by 3 grid.
 *
 * Seats go clockwise in turn order and spread evenly, up to the eight cells around the
 * middle. Returns one cell per seat, in seat order.
 */
export function seatCells(count: number): TableCell[] {
  return SEAT_CELLS[Math.min(Math.max(count, 0), 8)] ?? [];
}

/** A step of the phase indicator. */
export interface PhaseStep {
  phase: GamePhase;
  label: string;
  state: "done" | "current" | "next";
}

/** The phases the indicator shows, each with the phases it stands for. */
const STEPS: { phase: GamePhase; label: string; covers: GamePhase[] }[] = [
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
 * When `finished` is set every step is done.
 */
export function phaseSteps(phase: GamePhase | null, finished = false): PhaseStep[] {
  const current = STEPS.findIndex(
    (step) => phase !== null && step.covers.includes(phase),
  );

  return STEPS.map(({ phase: stepPhase, label }, index) => {
    let state: PhaseStep["state"] = "next";

    if (finished || (current >= 0 && index < current)) {
      state = "done";
    } else if (index === current) {
      state = "current";
    }

    return { phase: stepPhase, label, state };
  });
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

/** A curved vote arrow: its SVG path and the tip, with the angle it points at. */
export interface VoteArrow {
  path: string;
  tip: { x: number; y: number; angle: number };
}

/** The point where a line from the centre of a box towards a direction leaves the box. */
function edgePoint(rect: BoardRect, dx: number, dy: number): { x: number; y: number } {
  const cx = rect.x + rect.width / 2;
  const cy = rect.y + rect.height / 2;
  const scale = Math.min(
    dx === 0 ? Infinity : rect.width / 2 / Math.abs(dx),
    dy === 0 ? Infinity : rect.height / 2 / Math.abs(dy),
  );

  return { x: cx + dx * scale, y: cy + dy * scale };
}

/**
 * The arrow of a vote from the voter's card to the target's card.
 *
 * It runs from edge to edge, leaves `gap` pixels before the target and bends to its
 * left by `bend` times its length, so two votes between the same seats do not overlap.
 */
export function voteArrow({
  from,
  to,
  bend = 0.18,
  gap = 6,
}: {
  from: BoardRect;
  to: BoardRect;
  bend?: number;
  gap?: number;
}): VoteArrow {
  const dx = to.x + to.width / 2 - (from.x + from.width / 2);
  const dy = to.y + to.height / 2 - (from.y + from.height / 2);
  const start = edgePoint(from, dx, dy);
  const edge = edgePoint(to, -dx, -dy);
  const length = Math.hypot(edge.x - start.x, edge.y - start.y) || 1;
  const ux = (edge.x - start.x) / length;
  const uy = (edge.y - start.y) / length;
  const end = { x: edge.x - ux * gap, y: edge.y - uy * gap };
  const control = {
    x: (start.x + end.x) / 2 + uy * bend * length,
    y: (start.y + end.y) / 2 - ux * bend * length,
  };
  const angle = (Math.atan2(end.y - control.y, end.x - control.x) * 180) / Math.PI;
  const round = (value: number) => Math.round(value * 10) / 10;

  return {
    path: `M ${round(start.x)} ${round(start.y)} Q ${round(control.x)} ${round(control.y)} ${round(end.x)} ${round(end.y)}`,
    tip: { x: round(end.x), y: round(end.y), angle: round(angle) },
  };
}
