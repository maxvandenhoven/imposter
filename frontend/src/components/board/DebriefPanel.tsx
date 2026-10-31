import { Coins } from "lucide-react";

import type { CatalogModel } from "@/api/types";
import { RoleBadge } from "@/components/board/RoleBadge";
import { SeatAvatar } from "@/components/board/SeatAvatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DebriefSeatView, DebriefTurnView } from "@/lib/debrief";
import { formatCost, formatTokens, phaseTitle } from "@/lib/table";

/** What a turn was, in words: the clue or statement, the vote or the guess. */
function turnText(turn: DebriefTurnView, names: Map<number, string>): string {
  switch (turn.kind) {
    case "clue":
      return turn.text === null ? "Passed" : `Clue: ${turn.text}`;
    case "statement":
      return turn.text ?? "Passed";
    case "vote":
      return turn.target === null
        ? "Abstained"
        : `Voted for ${names.get(turn.target) ?? `seat ${turn.target}`}`;
    case "guess":
      return `Guessed: ${turn.text ?? ""}`;
    case "word_said":
      return `Said the secret word: ${turn.text ?? ""}`;
  }
}

/** One player: the reasoning of each turn on the left, the reflection on the right. */
function DebriefCard({
  seat,
  names,
  model,
}: {
  seat: DebriefSeatView;
  names: Map<number, string>;
  model: CatalogModel | undefined;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-3">
          <SeatAvatar model={model} role={seat.role} />
          <span>{seat.name}</span>
          <RoleBadge role={seat.role} />
          <span className="text-sm font-normal text-muted-foreground">
            {model?.display_name ?? seat.modelId ?? "Unknown model"}
          </span>
          <Badge variant="secondary" className="ml-auto gap-1.5 tabular-nums">
            <Coins className="text-speaking" />
            {formatCost(seat.costUsd)} · {formatTokens(seat.tokens)} tokens
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <section className="flex flex-col gap-3">
          <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            In the moment
          </h3>
          {seat.turns.map((turn) => (
            <div key={turn.key} className="flex flex-col gap-1">
              <p className="text-xs text-muted-foreground">
                {phaseTitle(turn.phase, turn.round)}
              </p>
              <p className="font-medium">{turnText(turn, names)}</p>
              {turn.reasoning !== "" && (
                <p className="rounded-lg bg-muted px-3 py-2 text-sm whitespace-pre-wrap text-muted-foreground">
                  {turn.reasoning}
                </p>
              )}
            </div>
          ))}
          {seat.turns.length === 0 && (
            <p className="text-sm text-muted-foreground">This player never got a turn.</p>
          )}
        </section>
        <section className="flex flex-col gap-3">
          <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Looking back
          </h3>
          <p className="rounded-lg bg-secondary px-3 py-2 text-sm whitespace-pre-wrap text-secondary-foreground">
            {seat.reflection ?? "No reflection was given."}
          </p>
        </section>
      </CardContent>
    </Card>
  );
}

/**
 * The debrief of a finished game: per player the role, model, clues, statements and
 * vote with the reasoning written at each turn next to the reflection after the reveal,
 * and the tokens and cost.
 */
export function DebriefPanel({
  seats,
  models,
}: {
  seats: DebriefSeatView[];
  models: Map<string, CatalogModel>;
}) {
  const names = new Map(seats.map((seat) => [seat.seat, seat.name]));

  return (
    <section aria-label="Debrief" className="flex flex-col gap-4">
      <h2 className="font-heading text-lg font-semibold">Debrief</h2>
      <div className="grid gap-4 2xl:grid-cols-2">
        {seats.map((seat) => (
          <DebriefCard
            key={seat.seat}
            seat={seat}
            names={names}
            model={seat.modelId === null ? undefined : models.get(seat.modelId)}
          />
        ))}
      </div>
    </section>
  );
}
