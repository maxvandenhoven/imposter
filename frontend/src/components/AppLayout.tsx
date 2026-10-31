import type { ReactNode } from "react";

/** The page frame: the app's name on top and the view below it. */
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-6 sm:px-8">
      <header className="flex items-center gap-3">
        <img src="/favicon.svg" alt="" className="size-8" />
        <div>
          <h1 className="font-heading text-xl font-semibold tracking-tight">Imposter</h1>
          <p className="text-sm text-muted-foreground">
            Language models play the social deduction game.
          </p>
        </div>
      </header>
      <main className="flex flex-1 flex-col gap-6">{children}</main>
    </div>
  );
}
