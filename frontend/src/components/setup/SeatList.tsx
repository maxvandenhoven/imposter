import { Plus, Shuffle, VenetianMask, X } from "lucide-react";

import type { CatalogModel } from "@/api/types";
import { ModelLogo } from "@/components/ModelLogo";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Toggle } from "@/components/ui/toggle";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { MAX_PLAYERS, MIN_PLAYERS, randomLineup, type SetupSeat } from "@/lib/setup";

/**
 * The seats of the game, each with a model, which can be added, removed and shuffled.
 *
 * A seat can be chosen as an imposter. Without a choice the imposters are random.
 */
export function SeatList({
  seats,
  models,
  onChange,
}: {
  seats: SetupSeat[];
  models: CatalogModel[];
  onChange: (seats: SetupSeat[]) => void;
}) {
  const byId = new Map(models.map((model) => [model.id, model]));

  const setSeat = (index: number, change: Partial<SetupSeat>) => {
    onChange(
      seats.map((seat, other) => (other === index ? { ...seat, ...change } : seat)),
    );
  };

  return (
    <div className="flex flex-col gap-2">
      <ol className="flex flex-col gap-2">
        {seats.map(({ modelId, imposter }, index) => (
          <li key={index} className="flex items-center gap-2">
            <span className="w-14 shrink-0 text-sm text-muted-foreground">
              Seat {index + 1}
            </span>
            <Select
              value={modelId}
              onValueChange={(value) => {
                setSeat(index, { modelId: value });
              }}
            >
              <SelectTrigger
                className="w-full sm:w-72"
                aria-label={`Model of seat ${index + 1}`}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {models.map((model) => (
                  <SelectItem key={model.id} value={model.id}>
                    <ModelLogo model={model} />
                    {model.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Tooltip>
              <TooltipTrigger asChild>
                <Toggle
                  variant="outline"
                  size="sm"
                  aria-label={`Seat ${index + 1} is an imposter`}
                  pressed={imposter}
                  onPressedChange={(pressed) => {
                    setSeat(index, { imposter: pressed });
                  }}
                  className="text-muted-foreground aria-pressed:border-imposter aria-pressed:bg-imposter aria-pressed:text-white aria-pressed:hover:bg-imposter/90"
                >
                  <VenetianMask />
                </Toggle>
              </TooltipTrigger>
              <TooltipContent>
                {imposter ? "This player is an imposter" : "Make this player an imposter"}
              </TooltipContent>
            </Tooltip>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Remove seat ${index + 1}`}
              title={`Remove seat ${index + 1}`}
              disabled={seats.length <= MIN_PLAYERS}
              onClick={() => {
                onChange(seats.filter((_, other) => other !== index));
              }}
            >
              <X />
            </Button>
            {byId.get(modelId) === undefined && (
              <span className="text-sm text-destructive">Unknown model</span>
            )}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={seats.length >= MAX_PLAYERS || models.length === 0}
          onClick={() => {
            const modelId = seats.at(-1)?.modelId ?? models[0]?.id ?? "";
            onChange([...seats, { modelId, imposter: false }]);
          }}
        >
          <Plus data-icon="inline-start" />
          Add seat
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            const lineup = randomLineup(
              models.map((model) => model.id),
              seats.length,
            );
            onChange(
              lineup.map((modelId, index) => ({
                modelId,
                imposter: seats[index]?.imposter ?? false,
              })),
            );
          }}
        >
          <Shuffle data-icon="inline-start" />
          Randomise lineup
        </Button>
      </div>
    </div>
  );
}
