import type { ReactNode } from "react";

/**
 * The page frame. The setup has a dark bar across the top with the app's name, above the
 * view. The board is wide and brings its own dark header bar, with the logo, so the
 * frame leaves the whole width to it.
 */
export function AppLayout({
  children,
  wide = false,
}: {
  children: ReactNode;
  wide?: boolean;
}) {
  if (wide) {
    return <main className="flex min-h-screen flex-col">{children}</main>;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="night border-b bg-background text-foreground">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-8">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <h1 className="font-heading text-xl font-semibold tracking-tight">
              Imposter
            </h1>
            <p className="text-sm text-muted-foreground">
              Language models play the social deduction game.
            </p>
          </div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 sm:px-8">
        {children}
      </main>
    </div>
  );
}
