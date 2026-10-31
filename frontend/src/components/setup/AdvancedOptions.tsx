import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { NumberField } from "@/components/setup/NumberField";
import { OptionSwitch } from "@/components/setup/OptionSwitch";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  CLUE_ROUNDS,
  DISCUSSION_ROUNDS,
  maxImposters,
  type SetupForm,
  TEMPERATURE,
} from "@/lib/setup";

/** The options most games keep at their defaults, collapsed until opened. */
export function AdvancedOptions({
  form,
  onChange,
}: {
  form: SetupForm;
  onChange: (patch: Partial<SetupForm>) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="flex flex-col gap-4">
      <CollapsibleTrigger asChild>
        <Button variant="ghost" className="self-start">
          <ChevronDown
            data-icon="inline-start"
            className={open ? "rotate-180 transition-transform" : "transition-transform"}
          />
          Advanced
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <NumberField
            id="clue-rounds"
            label="Clue rounds"
            min={CLUE_ROUNDS.min}
            max={CLUE_ROUNDS.max}
            value={form.clueRounds}
            onChange={(clueRounds) => {
              onChange({ clueRounds });
            }}
          />
          <NumberField
            id="discussion-rounds"
            label="Discussion rounds"
            min={DISCUSSION_ROUNDS.min}
            max={DISCUSSION_ROUNDS.max}
            value={form.discussionRounds}
            onChange={(discussionRounds) => {
              onChange({ discussionRounds });
            }}
          />
          <NumberField
            id="imposters"
            label="Imposters"
            min={1}
            max={Math.max(1, maxImposters(form.seats.length))}
            value={form.imposterCount}
            onChange={(imposterCount) => {
              onChange({ imposterCount });
            }}
          />
          <NumberField
            id="statement-cap"
            label="Statement word cap"
            min={1}
            value={form.statementWordCap}
            onChange={(statementWordCap) => {
              onChange({ statementWordCap });
            }}
          />
          <NumberField
            id="reasoning-cap"
            label="Reasoning word cap"
            min={1}
            value={form.reasoningWordCap}
            onChange={(reasoningWordCap) => {
              onChange({ reasoningWordCap });
            }}
          />
          <NumberField
            id="token-budget"
            label="Token budget"
            description="The game is aborted when its players use more."
            min={1}
            value={form.tokenBudget}
            onChange={(tokenBudget) => {
              onChange({ tokenBudget });
            }}
          />
        </div>
        <OptionSwitch
          id="model-clue-check"
          label="Model clue check"
          description="A model judges every clue that passes the code checks, to catch synonyms and translations."
          checked={form.modelClueCheck}
          onChange={(modelClueCheck) => {
            onChange({ modelClueCheck });
          }}
        />
        <OptionSwitch
          id="temperature-override"
          label="Temperature override"
          description="Sample every player at the same temperature instead of each model's own."
          checked={form.temperature !== null}
          onChange={(override) => {
            onChange({ temperature: override ? 1 : null });
          }}
        />
        {form.temperature !== null && (
          <div className="sm:w-48">
            <NumberField
              id="temperature"
              label="Temperature"
              min={TEMPERATURE.min}
              max={TEMPERATURE.max}
              step={0.1}
              value={form.temperature}
              onChange={(temperature) => {
                onChange({ temperature });
              }}
            />
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
