import { GripVertical, Plus, Shuffle, VenetianMask, X } from "lucide-react";
import { Reorder, useDragControls } from "motion/react";

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
import {
  imposterCount,
  MAX_PLAYERS,
  MIN_PLAYERS,
  moveSeat,
  newSeat,
  randomImposters,
  randomLineup,
  removeSeat,
  type SetupSeat,
} from "@/lib/setup";

/**
 * One seat: a drag handle, its model, the imposter mask and a remove button.
 *
 * The row is dragged by its handle only, so the select and the buttons keep working.
 * The handle also moves the seat with the up and down arrow keys.
 */
function SeatRow({
  seat,
  index,
  count,
  models,
  known,
  onChange,
  onMove,
  onRemove,
}: {
  seat: SetupSeat;
  index: number;
  count: number;
  models: CatalogModel[];
  known: boolean;
  onChange: (change: Partial<SetupSeat>) => void;
  onMove: (to: number) => void;
  onRemove: () => void;
}) {
  const controls = useDragControls();
  const number = index + 1;

  return (
    <Reorder.Item
      value={seat}
      dragListener={false}
      dragControls={controls}
      className="relative flex items-center gap-2 rounded-lg bg-card"
      whileDrag={{ scale: 1.02, boxShadow: "0 8px 24px rgb(0 0 0 / 0.12)", zIndex: 10 }}
    >
      <button
        type="button"
        aria-label={`Move seat ${number}`}
        title="Drag to reorder, or use the arrow keys"
        className="flex h-8 w-5 shrink-0 cursor-grab touch-none items-center justify-center rounded-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
        onPointerDown={(event) => {
          controls.start(event);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowUp" && index > 0) {
            event.preventDefault();
            onMove(index - 1);
          } else if (event.key === "ArrowDown" && index < count - 1) {
            event.preventDefault();
            onMove(index + 1);
          }
        }}
      >
        <GripVertical className="size-4" />
      </button>
      <span className="w-14 shrink-0 text-sm text-muted-foreground">Seat {number}</span>
      <Select
        value={seat.modelId}
        onValueChange={(value) => {
          onChange({ modelId: value });
        }}
      >
        <SelectTrigger
          className="w-full min-w-0 flex-1"
          aria-label={`Model of seat ${number}`}
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
            aria-label={`Seat ${number} is an imposter`}
            pressed={seat.imposter}
            onPressedChange={(pressed) => {
              onChange({ imposter: pressed });
            }}
            className="text-muted-foreground aria-pressed:border-imposter aria-pressed:bg-imposter aria-pressed:text-white aria-pressed:hover:bg-imposter/90"
          >
            <VenetianMask />
          </Toggle>
        </TooltipTrigger>
        <TooltipContent>
          {seat.imposter ? "This player is an imposter" : "Make this player an imposter"}
        </TooltipContent>
      </Tooltip>
      <Button
        variant="ghost"
        size="icon"
        aria-label={`Remove seat ${number}`}
        title={`Remove seat ${number}`}
        disabled={count <= MIN_PLAYERS}
        onClick={onRemove}
      >
        <X />
      </Button>
      {!known && <span className="text-sm text-destructive">Unknown model</span>}
    </Reorder.Item>
  );
}

/**
 * The seats of the game, each with a model, which can be added, removed, reordered and
 * shuffled.
 *
 * The seats chosen with the mask are the imposters, and their number is the number of
 * imposters. "Randomise imposters" moves the masks to random seats, keeping their number.
 * Dragging a seat by its handle moves it with its model and mask.
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
  const known = new Set(models.map((model) => model.id));

  const setSeat = (index: number, change: Partial<SetupSeat>) => {
    onChange(
      seats.map((seat, other) => (other === index ? { ...seat, ...change } : seat)),
    );
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          onClick={() => {
            const lineup = randomLineup(
              models.map((model) => model.id),
              seats.length,
            );
            onChange(
              lineup.map((modelId, index) => ({
                ...newSeat(modelId),
                imposter: seats[index]?.imposter ?? false,
              })),
            );
          }}
        >
          <Shuffle data-icon="inline-start" />
          Randomise lineup
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            onChange(randomImposters(seats));
          }}
        >
          <VenetianMask data-icon="inline-start" />
          Randomise imposters
        </Button>
        <span className="ml-auto text-sm text-muted-foreground">
          {imposterCount(seats) === 1
            ? "1 imposter"
            : `${imposterCount(seats)} imposters`}
        </span>
      </div>
      <Reorder.Group
        as="ol"
        axis="y"
        values={seats}
        onReorder={onChange}
        className="flex flex-col gap-2"
      >
        {seats.map((seat, index) => (
          <SeatRow
            key={seat.id}
            seat={seat}
            index={index}
            count={seats.length}
            models={models}
            known={known.has(seat.modelId)}
            onChange={(change) => {
              setSeat(index, change);
            }}
            onMove={(to) => {
              onChange(moveSeat({ seats, from: index, to }));
            }}
            onRemove={() => {
              onChange(removeSeat(seats, index));
            }}
          />
        ))}
      </Reorder.Group>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={seats.length >= MAX_PLAYERS || models.length === 0}
          onClick={() => {
            const modelId = seats.at(-1)?.modelId ?? models[0]?.id ?? "";
            onChange([...seats, newSeat(modelId)]);
          }}
        >
          <Plus data-icon="inline-start" />
          Add seat
        </Button>
      </div>
    </div>
  );
}
