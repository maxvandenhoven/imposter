import { PartyPopper, VenetianMask } from "lucide-react";
import { motion } from "motion/react";

import type { OutcomeView } from "@/lib/boardView";

/** The outcome of the game, as a banner in the colour of the side that won. */
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
      className="relative flex items-center gap-4 overflow-hidden rounded-2xl px-6 py-4 text-white shadow-lg data-[winner=civilians]:bg-civilian data-[winner=imposters]:bg-imposter"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-10 -right-6 size-40 rounded-full bg-white/10"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute right-32 -bottom-16 size-32 rounded-full bg-white/8"
      />
      <motion.span
        initial={{ rotate: -20, scale: 0.6 }}
        animate={{ rotate: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 10, delay: 0.2 }}
        className="flex size-14 shrink-0 items-center justify-center rounded-full bg-white/20"
      >
        <Icon className="size-8" />
      </motion.span>
      <div className="relative">
        <p className="text-sm font-medium tracking-wider uppercase opacity-85">
          {imposters ? "Imposters win" : "Civilians win"}
        </p>
        <h2 className="font-heading text-2xl font-bold tracking-tight xl:text-3xl">
          {outcome.title}
        </h2>
        <p className="opacity-90">{outcome.detail}</p>
      </div>
    </motion.section>
  );
}
