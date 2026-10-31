import { useEffect } from "react";

import type { GamePlayback } from "@/lib/playback";

/** Whether a key press happens in a field, where the arrow keys move the text cursor. */
function typingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName))
  );
}

/**
 * Step the playback with the arrow keys: left for the previous event, right for the
 * next, and with shift for the previous and next phase.
 */
export function usePlaybackKeys(
  playback: GamePlayback,
  onChange: (change: (playback: GamePlayback) => void) => void,
): void {
  useEffect(() => {
    const press = (event: KeyboardEvent) => {
      if (
        typingTarget(event.target) ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        (event.key !== "ArrowLeft" && event.key !== "ArrowRight")
      ) {
        return;
      }

      event.preventDefault();
      const forward = event.key === "ArrowRight";

      onChange((current) => {
        if (event.shiftKey) {
          if (forward) {
            current.nextPhase();
          } else {
            current.previousPhase();
          }
        } else if (forward) {
          current.stepForward();
        } else {
          current.stepBack();
        }
      });
    };
    window.addEventListener("keydown", press);

    return () => {
      window.removeEventListener("keydown", press);
    };
  }, [playback, onChange]);
}
