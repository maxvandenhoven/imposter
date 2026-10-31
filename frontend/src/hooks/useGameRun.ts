import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { playGame } from "@/api/gameStream";
import type { GameRequest } from "@/api/types";
import {
  type BoardAction,
  boardReducer,
  type BoardState,
  INITIAL_BOARD,
} from "@/lib/board";
import { GamePlayback, GameTimeline } from "@/lib/playback";

type GameRunAction = BoardAction | { type: "restart" };

function gameRunReducer(state: BoardState, action: GameRunAction): BoardState {
  return action.type === "restart" ? INITIAL_BOARD : boardReducer(state, action);
}

/**
 * Run games one at a time and keep the live board and the playback of the current one.
 *
 * `start` creates a game and streams it into the live board and into the timeline that
 * the playback plays at the audience's pace. `stop` closes the stream, which aborts the
 * game on the server. The stream is also closed when the component unmounts.
 */
export function useGameRun() {
  const [board, dispatch] = useReducer(gameRunReducer, INITIAL_BOARD);
  const [playback, setPlayback] = useState(() => new GamePlayback(new GameTimeline()));
  const controller = useRef<AbortController | null>(null);

  const start = useCallback((request: GameRequest) => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    const timeline = new GameTimeline();
    setPlayback(new GamePlayback(timeline));
    dispatch({ type: "restart" });

    // Events of a game that was replaced do not reach the board of the new one.
    const live = () => controller.current === current;
    const send = (action: BoardAction) => {
      if (live()) {
        dispatch(action);
      }
    };

    void playGame({
      request,
      signal: current.signal,
      handlers: {
        onSession: (gameId) => {
          send({ type: "session", gameId });
        },
        onGameEvent: (event) => {
          if (live()) {
            timeline.push({ kind: "event", event });
          }

          send({ type: "game_event", event });
        },
        onAnswer: (answer) => {
          if (live()) {
            timeline.push({ kind: "answer", answer });
          }
        },
        onError: (message) => {
          send({ type: "error", message });
        },
      },
    }).then(() => {
      send({ type: "ended", stopped: current.signal.aborted });
    });
  }, []);

  const stop = useCallback(() => {
    controller.current?.abort();
  }, []);

  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );

  return { board, playback, start, stop };
}
