import { ListEnd, Pause, Play, Radio, SkipForward } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Toggle } from "@/components/ui/toggle";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { GamePlayback } from "@/lib/playback";

/** The speeds the audience can pick. */
const SPEEDS = [1, 2, 4];

/**
 * The playback controls, floating under the board: play and pause, the next response,
 * stopping after each round, the speed, and how far playback is behind the live game.
 */
export function PlaybackBar({
  playback,
  onChange,
}: {
  playback: GamePlayback;
  onChange: (change: (playback: GamePlayback) => void) => void;
}) {
  const behind = playback.responsesBehind;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-40 flex justify-center px-4">
      <div className="pointer-events-auto flex flex-wrap items-center gap-2 rounded-full border bg-card/95 px-3 py-2 shadow-lg backdrop-blur">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              className="rounded-full"
              aria-label={playback.playing ? "Pause" : "Play"}
              onClick={() => {
                onChange((current) => {
                  if (current.playing) {
                    current.pause();
                  } else {
                    current.play();
                  }
                });
              }}
            >
              {playback.playing ? <Pause /> : <Play />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{playback.playing ? "Pause" : "Play"}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="rounded-full"
              onClick={() => {
                onChange((current) => {
                  current.step();
                });
              }}
            >
              <SkipForward data-icon="inline-start" />
              Next response
            </Button>
          </TooltipTrigger>
          <TooltipContent>Play until the next answer is in, then pause.</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Toggle
              variant="outline"
              size="sm"
              className="rounded-full aria-pressed:border-primary aria-pressed:bg-secondary aria-pressed:text-secondary-foreground"
              pressed={playback.pauseAfterRounds}
              onPressedChange={(pressed) => {
                onChange((current) => {
                  current.pauseAfterRounds = pressed;
                });
              }}
            >
              <ListEnd />
              Pause after rounds
            </Toggle>
          </TooltipTrigger>
          <TooltipContent>
            Pause before every new round, so a round can be discussed.
          </TooltipContent>
        </Tooltip>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          aria-label="Speed"
          value={String(playback.speed)}
          onValueChange={(value) => {
            // A click on the pressed item clears the value, which keeps the speed.
            if (value !== "") {
              onChange((current) => {
                current.speed = Number(value);
              });
            }
          }}
        >
          {SPEEDS.map((speed) => (
            <ToggleGroupItem key={speed} value={String(speed)} className="tabular-nums">
              {speed}×
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {playback.pausedFor === "round" && (
          <span className="px-1 text-sm text-muted-foreground">Round over</span>
        )}
        {behind > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="rounded-full text-primary"
            onClick={() => {
              onChange((current) => {
                current.goLive();
              });
            }}
          >
            <Radio data-icon="inline-start" />
            {behind === 1 ? "1 response behind" : `${behind} responses behind`} · Go live
          </Button>
        )}
      </div>
    </div>
  );
}
