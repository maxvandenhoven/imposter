import { useCallback, useEffect, useReducer, useRef } from "react";

import { playGame } from "@/api/gameStream";
import type { GameRequest } from "@/api/types";
import {
  type BoardAction,
  boardReducer,
  type BoardState,
  INITIAL_BOARD,
} from "@/lib/board";

type GameRunAction = BoardAction | { type: "restart" };

function gameRunReducer(state: BoardState, action: GameRunAction): BoardState {
  return action.type === "restart" ? INITIAL_BOARD : boardReducer(state, action);
}

/**
 * Run games one at a time and keep the board of the current one.
 *
 * `start` creates a game and streams it into the board, `stop` closes the stream, which
 * aborts the game on the server. The stream is also closed when the component unmounts.
 */
export function useGameRun() {
  const [board, dispatch] = useReducer(gameRunReducer, INITIAL_BOARD);
  const controller = useRef<AbortController | null>(null);

  const start = useCallback((request: GameRequest) => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    dispatch({ type: "restart" });

    // Events of a game that was replaced do not reach the board of the new one.
    const send = (action: BoardAction) => {
      if (controller.current === current) {
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
          send({ type: "game_event", event });
        },
        onAnswer: (answer) => {
          send({ type: "answer", answer });
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

  return { board, start, stop };
}
