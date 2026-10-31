import { cn } from "cn";
import type { ReactNode } from "react";

/**
 * The page frame: the view, with the app's name on top of the setup. The board is wide
 * and has no title, since its header carries the logo.
 */
export function AppLayout({
  children,
  wide = false,
}: {
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div
      className={cn(
        "mx-auto flex min-h-screen flex-col gap-5 px-4 py-5 sm:px-8",
        wide ? "max-w-[120rem]" : "max-w-6xl",
      )}
    >
      {!wide && (
        <header className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <h1 className="font-heading text-xl font-semibold tracking-tight">
              Imposter
            </h1>
            <p className="text-sm text-muted-foreground">
              Language models play the social deduction game.
            </p>
          </div>
        </header>
      )}
      <main className="flex flex-1 flex-col gap-6">{children}</main>
    </div>
  );
}
