import { RotateCcw, Square } from "lucide-react";

import { EventList } from "@/components/board/EventList";
import { SeatList } from "@/components/board/SeatList";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLeaveWarning } from "@/hooks/useLeaveWarning";
import { type BoardState, type BoardStatus, seatNames, thinkingSeats } from "@/lib/board";

const STATUS_LABELS: Record<BoardStatus, string> = {
  running: "Live",
  finished: "Finished",
  aborted: "Aborted",
  failed: "Failed",
  stopped: "Stopped",
};

/** The board of a game: its seats, its events as they arrive and its errors. */
export function BoardPage({
  board,
  onStop,
  onNewGame,
}: {
  board: BoardState;
  onStop: () => void;
  onNewGame: () => void;
}) {
  const running = board.status === "running";
  const names = seatNames(board.events);
  const thinking = running ? thinkingSeats(board.events) : [];
  // Leaving the page closes the stream, which aborts the game.
  useLeaveWarning(running);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant={running ? "default" : "secondary"}>
          {STATUS_LABELS[board.status]}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {board.events.length} events
        </span>
        <div className="ml-auto flex gap-2">
          {running ? (
            <Button variant="destructive" onClick={onStop}>
              <Square data-icon="inline-start" />
              Stop game
            </Button>
          ) : (
            <Button onClick={onNewGame}>
              <RotateCcw data-icon="inline-start" />
              New game
            </Button>
          )}
        </div>
      </div>
      {board.errors.map((message, index) => (
        <Alert key={index} variant="destructive">
          <AlertTitle>The game failed</AlertTitle>
          <AlertDescription className="whitespace-pre-wrap">{message}</AlertDescription>
        </Alert>
      ))}
      <SeatList names={names} thinking={thinking} answers={board.answers} />
      <Card>
        <CardHeader>
          <CardTitle>Events</CardTitle>
        </CardHeader>
        <CardContent>
          <EventList events={board.events} names={names} />
        </CardContent>
      </Card>
    </div>
  );
}
