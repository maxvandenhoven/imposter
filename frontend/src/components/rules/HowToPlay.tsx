import { cn } from "cn";
import {
  Megaphone,
  PartyPopper,
  ShieldCheck,
  type LucideIcon,
  VenetianMask,
} from "lucide-react";
import type { ReactNode } from "react";

import { STEP_ICONS } from "@/components/board/phaseIcons";
import { type DiagramPlayer, RuleDiagram } from "@/components/rules/RuleDiagram";
import { Card, CardContent } from "@/components/ui/card";

/** The secret word of every diagram. */
const WORD = "lighthouse";

/** The four players of the diagrams in seat order, with Charlie as the imposter. */
const ALICE: DiagramPlayer = { name: "Alice", role: "civilian", logo: "claude" };
const BOB: DiagramPlayer = { name: "Bob", role: "civilian", logo: "openai" };
const CHARLIE: DiagramPlayer = { name: "Charlie", role: "imposter", logo: "gemini" };
const DAVE: DiagramPlayer = { name: "Dave", role: "civilian", logo: "qwen" };

/** The players of a diagram: the four, with what the diagram shows about some of them. */
function lineup(
  changes: Partial<Record<string, Partial<DiagramPlayer>>>,
): DiagramPlayer[] {
  return [ALICE, BOB, CHARLIE, DAVE].map((player) => ({
    ...player,
    ...changes[player.name],
  }));
}

/** Everyone but the players named, out of focus. */
function quietExcept(...names: string[]): Record<string, Partial<DiagramPlayer>> {
  return Object.fromEntries(
    [ALICE, BOB, CHARLIE, DAVE]
      .filter((player) => !names.includes(player.name))
      .map((player) => [player.name, { quiet: true }]),
  );
}

/** One phase of the game: its icon, title and rules, with diagrams beside the text. */
function RuleSection({
  icon: Icon,
  step,
  title,
  children,
  diagrams,
}: {
  icon: LucideIcon | undefined;
  step: number;
  title: string;
  children: ReactNode;
  diagrams: ReactNode;
}) {
  const headingId = `rules-${step}`;

  return (
    <section aria-labelledby={headingId}>
      <Card className="py-5">
        <CardContent className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md shadow-primary/25">
                {Icon !== undefined && <Icon className="size-4.5" />}
              </span>
              <h3 id={headingId} className="font-heading text-lg font-semibold">
                <span className="mr-1.5 text-muted-foreground tabular-nums">{step}.</span>
                {title}
              </h3>
            </div>
            <div className="flex flex-col gap-2 text-sm leading-relaxed">{children}</div>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">{diagrams}</div>
        </CardContent>
      </Card>
    </section>
  );
}

/** One way the game can end, with the side that wins it. */
function OutcomeRow({
  icon: Icon,
  when,
  winner,
}: {
  icon: LucideIcon;
  when: string;
  winner: "civilians" | "imposters";
}) {
  return (
    <li className="flex items-center gap-3 rounded-lg bg-muted/60 px-3 py-2">
      <Icon className="size-4 shrink-0 text-muted-foreground" />
      <span className="flex-1 text-sm">{when}</span>
      <span
        data-winner={winner}
        className={cn(
          "flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
          "data-[winner=civilians]:bg-civilian/12 data-[winner=civilians]:text-civilian",
          "data-[winner=imposters]:bg-imposter data-[winner=imposters]:text-white",
        )}
      >
        {winner === "civilians" ? (
          <ShieldCheck className="size-3" />
        ) : (
          <VenetianMask className="size-3" />
        )}
        {winner === "civilians" ? "Civilians win" : "Imposters win"}
      </span>
    </li>
  );
}

/**
 * The rules of the game, one card per phase, each with small scenes built from the
 * pieces of the board that show what is allowed and what is not.
 */
export function HowToPlay() {
  return (
    <section aria-labelledby="how-to-play" className="flex flex-col gap-4">
      <div>
        <h2
          id="how-to-play"
          className="font-heading text-xl font-semibold tracking-tight"
        >
          How to play
        </h2>
        <p className="text-sm text-muted-foreground">
          In the scenes below a teal ring marks a civilian and a red ring an imposter.
          Speech bubbles point at the player who speaks, a green check marks an answer
          that follows the rules and a red cross one that breaks them.
        </p>
      </div>
      <RuleSection
        icon={VenetianMask}
        step={1}
        title="The secret word"
        diagrams={
          <>
            <RuleDiagram
              title="Who knows the word"
              players={lineup({
                Alice: { knows: WORD },
                Bob: { knows: WORD },
                Dave: { knows: WORD },
                Charlie: { knows: "???" },
              })}
              caption="Alice, Bob and Dave are civilians and know the word. Charlie is the imposter and does not."
            />
            <RuleDiagram
              title="With the imposter hint"
              players={lineup({
                ...quietExcept("Charlie"),
                Charlie: { knows: "coast" },
              })}
              caption="With the imposter hint option, Charlie gets a related word to start from."
            />
          </>
        }
      >
        <p>
          Every player except the imposters learns the same secret word. The imposters
          only know that they are imposters, and with more than one they do not know who
          the others are.
        </p>
        <p>
          The civilians want to find the imposters. The imposters want to blend in and
          work out the word.
        </p>
      </RuleSection>
      <RuleSection
        icon={STEP_ICONS.clue}
        step={2}
        title="Clues"
        diagrams={
          <>
            <RuleDiagram
              title="A good clue"
              players={lineup({
                ...quietExcept("Alice"),
                Alice: { says: "beam", mark: "good" },
              })}
              caption="The clue shows that Alice knows the word, without handing it to the imposter."
            />
            <RuleDiagram
              title="Saying the word"
              players={lineup({
                ...quietExcept("Bob"),
                Bob: { says: WORD, mark: "bad" },
              })}
              caption="The game ends at once. A civilian who says the word hands the win to the imposters."
            />
            <RuleDiagram
              title="Repeating a clue"
              players={lineup({
                ...quietExcept("Alice", "Dave"),
                Alice: { says: "beam", mark: "good" },
                Dave: { says: "beam", mark: "bad" },
              })}
              caption="Every clue must be new. A repeated clue is replaced by a pass."
            />
            <RuleDiagram
              title="The imposter bluffs"
              players={lineup({
                ...quietExcept("Charlie"),
                Charlie: { says: "tall", mark: "good", knows: "???" },
              })}
              caption="Charlie does not know the word, so the imposter gives a vague clue that fits the clues so far."
            />
          </>
        }
      >
        <p>
          The game has a few clue rounds. In each round every player, in turn, gives one
          word that is related to the secret word.
        </p>
        <p>
          A clue may never be the secret word itself, not even as part of a longer word,
          and never a clue that anyone gave before. A clue that breaks a rule is replaced
          by a pass.
        </p>
      </RuleSection>
      <RuleSection
        icon={STEP_ICONS.discussion}
        step={3}
        title="Discussion"
        diagrams={
          <>
            <RuleDiagram
              title="An accusation"
              players={lineup({
                ...quietExcept("Bob", "Charlie"),
                Bob: { says: "Charlie's “tall” is too vague." },
                Charlie: { suspected: true },
              })}
              caption="Bob points at the clue that fits the word least."
            />
            <RuleDiagram
              title="A defence"
              players={lineup({
                ...quietExcept("Bob", "Charlie"),
                Bob: { suspected: true },
                Charlie: { says: "Bob passed twice!" },
              })}
              caption="Charlie turns the suspicion on someone else."
            />
          </>
        }
      >
        <p>
          In the discussion rounds every player, in turn, makes a short public statement
          to accuse, defend or ask a question.
        </p>
        <p>The secret word may not be said here either.</p>
      </RuleSection>
      <RuleSection
        icon={STEP_ICONS.vote}
        step={4}
        title="Vote"
        diagrams={
          <>
            <RuleDiagram
              title="The imposter is caught"
              players={lineup({
                Alice: { votedBy: [] },
                Bob: { votedBy: [] },
                Dave: { votedBy: ["Charlie"] },
                Charlie: { votedBy: ["Alice", "Bob", "Dave"], caught: true },
              })}
              caption="Charlie has the most votes and is caught."
            />
            <RuleDiagram
              title="A tie"
              players={lineup({
                Alice: { votedBy: ["Dave", "Charlie"] },
                Bob: { votedBy: [] },
                Dave: { votedBy: [] },
                Charlie: { votedBy: ["Alice", "Bob"] },
              })}
              caption="Alice and Charlie have two votes each. A tie catches nobody."
            />
          </>
        }
      >
        <p>
          Every player votes in secret for one other player. The votes are revealed
          together, and the player with the most votes is caught.
        </p>
        <p>When the most votes are tied, nobody is caught.</p>
      </RuleSection>
      <RuleSection
        icon={STEP_ICONS.guess}
        step={5}
        title="Guess"
        diagrams={
          <>
            <RuleDiagram
              title="A right guess"
              players={lineup({
                ...quietExcept("Charlie"),
                Charlie: { says: WORD, mark: "good", caught: true },
              })}
              caption="The caught imposter guesses the word and steals the win."
            />
            <RuleDiagram
              title="A wrong guess"
              players={lineup({
                ...quietExcept("Charlie"),
                Charlie: { says: "tower", mark: "bad", caught: true },
              })}
              caption="The guess misses, so the civilians win."
            />
          </>
        }
      >
        <p>
          Every imposter makes one guess at the secret word. It is the only moment anyone
          may say it.
        </p>
      </RuleSection>
      <RuleSection
        icon={STEP_ICONS.outcome}
        step={6}
        title="Who wins"
        diagrams={
          <ul className="flex flex-col gap-2 sm:col-span-2">
            <OutcomeRow
              icon={VenetianMask}
              when="An imposter is not caught."
              winner="imposters"
            />
            <OutcomeRow
              icon={STEP_ICONS.guess ?? VenetianMask}
              when="A caught imposter guesses the word."
              winner="imposters"
            />
            <OutcomeRow
              icon={PartyPopper}
              when="The caught imposters guess wrong."
              winner="civilians"
            />
            <OutcomeRow
              icon={Megaphone}
              when="A civilian says the word in a clue or statement."
              winner="imposters"
            />
            <OutcomeRow
              icon={Megaphone}
              when="An imposter says the word in a clue or statement."
              winner="civilians"
            />
          </ul>
        }
      >
        <p>
          The word and the roles are revealed to everyone. In the debrief every player
          then reflects on how it played.
        </p>
      </RuleSection>
    </section>
  );
}
