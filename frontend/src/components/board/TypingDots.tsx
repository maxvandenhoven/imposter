import { cn } from "cn";

/** Three bouncing dots that show a seat is writing. */
export function TypingDots({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="typing"
      className={cn("inline-flex items-center gap-1 text-speaking", className)}
    >
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="typing-dot size-1.5 rounded-full bg-current"
          style={{ animationDelay: `${index * 0.15}s` }}
        />
      ))}
    </span>
  );
}
