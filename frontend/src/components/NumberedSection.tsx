import { cn } from "cn";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * A panel with the look of a card, holding one or more numbered sections separated by
 * lines.
 */
export function SectionPanel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "divide-y rounded-xl bg-card text-card-foreground shadow-xs ring-1 ring-border",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * A numbered section of the setup page: its icon, number, title and introduction in a
 * fixed column on the left, and its content on the right. The setup form and the rules
 * share it, so their titles and contents start on the same lines whatever their height.
 */
export function NumberedSection({
  id,
  icon: Icon,
  step,
  title,
  intro,
  children,
}: {
  id: string;
  icon: LucideIcon | undefined;
  step: number;
  title: string;
  intro: ReactNode;
  children: ReactNode;
}) {
  const headingId = `${id}-heading`;

  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className="grid gap-5 px-6 py-6 md:grid-cols-[18rem_minmax(0,1fr)] md:gap-8"
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md shadow-primary/25">
            {Icon !== undefined && <Icon className="size-4.5" />}
          </span>
          <h3 id={headingId} className="font-heading text-lg font-semibold">
            <span className="mr-1.5 text-muted-foreground tabular-nums">{step}.</span>
            {title}
          </h3>
        </div>
        <div className="flex flex-col gap-2 pl-[2.875rem] text-sm leading-relaxed text-foreground/85">
          {intro}
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-5">{children}</div>
    </section>
  );
}
