import { cn } from "cn";
import { Vote } from "lucide-react";

/**
 * A ballot that landed on a seat, with the voter's name. A secret vote is dashed, a
 * revealed vote solid, and a ballot on a caught seat takes the imposter colour. Every
 * ballot of a size has the same width, so stacked and side by side ballots line up, and
 * a name too long for it is cut, with the whole name as its title. The small size, for
 * the rule diagrams, leaves out the icon to fit in a player's column.
 */
export function BallotChip({
  name,
  revealed,
  caught,
  size = "default",
}: {
  name: string;
  revealed: boolean;
  caught: boolean;
  size?: "sm" | "default";
}) {
  return (
    <span
      data-revealed={revealed}
      data-caught={caught}
      title={name}
      className={cn(
        "flex items-center justify-center gap-1 rounded-full border border-dashed border-primary/60 bg-primary/5 py-0.5 font-semibold whitespace-nowrap text-primary data-[caught=true]:border-imposter/60 data-[caught=true]:text-imposter data-[revealed=true]:border-solid data-[revealed=true]:border-transparent data-[revealed=true]:bg-primary data-[revealed=true]:text-primary-foreground data-[revealed=true]:data-[caught=true]:bg-imposter",
        size === "sm" ? "w-14 px-1 text-[0.65rem]" : "w-24 px-2 text-xs",
      )}
    >
      {size === "default" && <Vote className="size-3 shrink-0" />}
      <span className="truncate">{name}</span>
    </span>
  );
}
