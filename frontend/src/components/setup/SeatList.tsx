import { cn } from "cn";
import { GripVertical, Plus, Shuffle, VenetianMask, X } from "lucide-react";
import { type PointerEvent as ReactPointerEvent, useRef, useState } from "react";

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
  dragShift,
  dragTarget,
  moveSeat,
  newSeat,
  randomImposters,
  randomLineup,
  removeSeat,
  type SetupSeat,
} from "@/lib/setup";

/** A drag of a seat by its handle: where it started and how far the pointer moved. */
interface SeatDrag {
  from: number;
  /** The pointer's vertical position when the drag started. */
  startY: number;
  /** How far the pointer moved since, in pixels. */
  offset: number;
  /** The distance from one row to the next, in pixels. */
  step: number;
}

/**
 * One seat: a drag handle, its model, the imposter mask and a remove button.
 *
 * The row is dragged by its handle only, so the select and the buttons keep working,
 * and the handle also moves it with the up and down arrow keys. While a seat is dragged
 * the dragged row follows the pointer and the rows it passes slide aside by `shift`.
 * Otherwise the rows have no animation, so they move at once with the rest of the page.
 */
function SeatRow({
  seat,
  index,
  count,
  models,
  known,
  dragged,
  shift,
  onHandleDown,
  onChange,
  onMove,
  onRemove,
}: {
  seat: SetupSeat;
  index: number;
  count: number;
  models: CatalogModel[];
  known: boolean;
  /** The offset of this row while it is the one being dragged, else `null`. */
  dragged: number | null;
  /** How far this row steps aside while another row is dragged, else `null`. */
  shift: number | null;
  onHandleDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onChange: (change: Partial<SetupSeat>) => void;
  onMove: (to: number) => void;
  onRemove: () => void;
}) {
  const number = index + 1;
  const offset = dragged ?? shift;

  return (
    <li
      data-dragged={dragged !== null}
      data-seat-row
      className={cn(
        "relative flex items-center gap-2 rounded-lg bg-card data-[dragged=true]:z-10 data-[dragged=true]:shadow-lg data-[dragged=true]:ring-1 data-[dragged=true]:ring-border",
        shift !== null && "transition-transform duration-150 ease-out",
      )}
      style={offset === null ? undefined : { transform: `translateY(${offset}px)` }}
    >
      <button
        type="button"
        aria-label={`Move seat ${number}`}
        title="Drag to reorder, or use the arrow keys"
        className="flex h-8 w-5 shrink-0 cursor-grab touch-none items-center justify-center rounded-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
        onPointerDown={onHandleDown}
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
    </li>
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
  const [drag, setDrag] = useState<SeatDrag | null>(null);
  const list = useRef<HTMLOListElement>(null);
  const target =
    drag === null
      ? null
      : dragTarget({
          from: drag.from,
          offset: drag.offset,
          step: drag.step,
          count: seats.length,
        });

  /** Start dragging a seat by its handle, following the pointer until it is let go. */
  const startDrag = (index: number, event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) {
      return;
    }

    const rows = list.current?.querySelectorAll("[data-seat-row]") ?? [];
    const first = rows[0]?.getBoundingClientRect();
    const second = rows[1]?.getBoundingClientRect();
    const step = first && second ? second.top - first.top : (first?.height ?? 0);
    const startY = event.clientY;
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    setDrag({ from: index, startY, offset: 0, step });

    const move = (moveEvent: PointerEvent) => {
      setDrag((current) =>
        current === null ? null : { ...current, offset: moveEvent.clientY - startY },
      );
    };

    const end = (endEvent: PointerEvent) => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      const to = dragTarget({
        from: index,
        offset: endEvent.type === "pointerup" ? endEvent.clientY - startY : 0,
        step,
        count: seats.length,
      });
      setDrag(null);

      if (to !== index) {
        onChange(moveSeat({ seats, from: index, to }));
      }
    };

    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  };

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
      <ol ref={list} className="flex flex-col gap-2">
        {seats.map((seat, index) => (
          <SeatRow
            key={seat.id}
            seat={seat}
            index={index}
            count={seats.length}
            models={models}
            known={known.has(seat.modelId)}
            dragged={drag?.from === index ? drag.offset : null}
            shift={
              drag === null || target === null || drag.from === index
                ? null
                : dragShift({ index, from: drag.from, target, step: drag.step })
            }
            onHandleDown={(event) => {
              startDrag(index, event);
            }}
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
      </ol>
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
