import { useEffect } from "react";

/** Ask the browser to confirm before the page is left or reloaded while `active`. */
export function useLeaveWarning(active: boolean): void {
  useEffect(() => {
    if (!active) {
      return;
    }

    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);

    return () => {
      window.removeEventListener("beforeunload", warn);
    };
  }, [active]);
}
