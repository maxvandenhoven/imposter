import { useCallback, useEffect, useState } from "react";

import type { GamePlayback } from "@/lib/playback";

/**
 * The shortest time between two renders of a playing board, about 30 a second. Text is
 * written at a few dozen characters a second, so more renders would show no more.
 */
const RENDER_INTERVAL_MILLISECONDS = 33;

/**
 * Run a playback's clock on animation frames, and render again when its board changes
 * or new items arrive, at most every `RENDER_INTERVAL_MILLISECONDS`.
 *
 * Returns a function that wraps a change to the playback, such as a pause, so that the
 * component renders it at once.
 */
export function usePlaybackClock(playback: GamePlayback) {
  const [, setFrame] = useState(0);
  const rerender = useCallback(() => {
    setFrame((frame) => frame + 1);
  }, []);

  useEffect(() => {
    let last = performance.now();
    let lastRender = 0;
    let arrived = playback.timeline.length;
    let pending = false;
    let request = 0;

    const tick = (now: number) => {
      // A tab in the background gets no frames, so a long gap counts as one frame.
      const elapsed = Math.min(now - last, 250);
      last = now;

      // New items change how far behind playback is, also while it is paused.
      if (playback.advance(elapsed) || playback.timeline.length !== arrived) {
        arrived = playback.timeline.length;
        pending = true;
      }

      if (pending && now - lastRender >= RENDER_INTERVAL_MILLISECONDS) {
        pending = false;
        lastRender = now;
        rerender();
      }

      request = requestAnimationFrame(tick);
    };
    request = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(request);
    };
  }, [playback, rerender]);

  return useCallback(
    (change: (playback: GamePlayback) => void) => {
      change(playback);
      rerender();
    },
    [playback, rerender],
  );
}
