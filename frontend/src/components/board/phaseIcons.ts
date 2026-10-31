import {
  HelpCircle,
  Lightbulb,
  type LucideIcon,
  MessagesSquare,
  NotebookPen,
  Trophy,
  Vote,
} from "lucide-react";

import type { GamePhase } from "@/api/types";

/** The icon of each step of the phase indicator, shared with the rules of the game. */
export const STEP_ICONS: Partial<Record<GamePhase, LucideIcon>> = {
  clue: Lightbulb,
  discussion: MessagesSquare,
  vote: Vote,
  guess: HelpCircle,
  outcome: Trophy,
  debrief: NotebookPen,
};
