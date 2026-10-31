import type { GameEvent } from "@/api/types";
import { describeEvent } from "@/lib/board";

/** The engine events so far, newest last, one line each. */
export function EventList({
  events,
  names,
}: {
  events: GameEvent[];
  names: Map<number, string>;
}) {
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">Setting up the game…</p>;
  }

  return (
    <ol className="flex flex-col gap-1 text-sm">
      {events.map((event) => (
        <li
          key={event.seq}
          data-type={event.type}
          className="flex gap-3 data-[type=phase_started]:pt-3 data-[type=phase_started]:font-semibold data-[type=usage]:text-muted-foreground"
        >
          <span className="w-8 shrink-0 text-right text-muted-foreground tabular-nums">
            {event.seq}
          </span>
          <span>{describeEvent(event, names)}</span>
        </li>
      ))}
    </ol>
  );
}
