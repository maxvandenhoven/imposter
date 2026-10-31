import { PartyPopper, VenetianMask } from "lucide-react";
import { motion } from "motion/react";

import type { OutcomeView } from "@/lib/boardView";

/**
 * The outcome of the game, as a dark banner that stands out from the board, lit in the
 * colour of the side that won.
 */
export function OutcomeBanner({ outcome }: { outcome: OutcomeView }) {
  const imposters = outcome.winner === "imposters";
  const Icon = imposters ? VenetianMask : PartyPopper;

  return (
    <motion.section
      role="status"
      initial={{ opacity: 0, y: -16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
      data-winner={outcome.winner}
      className="group/banner relative flex items-center gap-4 overflow-hidden rounded-2xl border-l-8 bg-[#16131f] px-6 py-4 text-white shadow-xl ring-1 ring-white/10 data-[winner=civilians]:border-civilian data-[winner=imposters]:border-imposter"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-16 -right-10 size-56 rounded-full opacity-30 blur-2xl group-data-[winner=civilians]/banner:bg-civilian group-data-[winner=imposters]/banner:bg-imposter"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute right-40 -bottom-20 size-36 rounded-full bg-white/5"
      />
      <motion.span
        initial={{ rotate: -20, scale: 0.6 }}
        animate={{ rotate: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 10, delay: 0.2 }}
        className="flex size-14 shrink-0 items-center justify-center rounded-full text-white shadow-lg group-data-[winner=civilians]/banner:bg-civilian group-data-[winner=imposters]/banner:bg-imposter"
      >
        <Icon className="size-8" />
      </motion.span>
      <div className="relative">
        <p className="text-sm font-semibold tracking-wider uppercase group-data-[winner=civilians]/banner:text-civilian group-data-[winner=imposters]/banner:text-imposter">
          {imposters ? "Imposters win" : "Civilians win"}
        </p>
        <h2 className="font-heading text-2xl font-bold tracking-tight xl:text-3xl">
          {outcome.title}
        </h2>
        <p className="text-white/75">{outcome.detail}</p>
      </div>
    </motion.section>
  );
}
