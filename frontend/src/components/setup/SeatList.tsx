import { Plus, Shuffle, X } from "lucide-react";

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
import { MAX_PLAYERS, MIN_PLAYERS, randomLineup } from "@/lib/setup";

/** The seats of the game, each with a model, which can be added, removed and shuffled. */
export function SeatList({
  seats,
  models,
  onChange,
}: {
  seats: string[];
  models: CatalogModel[];
  onChange: (seats: string[]) => void;
}) {
  const byId = new Map(models.map((model) => [model.id, model]));

  const setSeat = (index: number, modelId: string) => {
    onChange(seats.map((seat, other) => (other === index ? modelId : seat)));
  };

  return (
    <div className="flex flex-col gap-2">
      <ol className="flex flex-col gap-2">
        {seats.map((modelId, index) => (
          <li key={index} className="flex items-center gap-2">
            <span className="w-14 shrink-0 text-sm text-muted-foreground">
              Seat {index + 1}
            </span>
            <Select
              value={modelId}
              onValueChange={(value) => {
                setSeat(index, value);
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
            onChange([...seats, seats.at(-1) ?? models[0]?.id ?? ""]);
          }}
        >
          <Plus data-icon="inline-start" />
          Add seat
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            onChange(
              randomLineup(
                models.map((model) => model.id),
                seats.length,
              ),
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
