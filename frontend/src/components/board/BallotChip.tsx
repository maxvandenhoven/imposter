import { cn } from "cn";
import { Vote } from "lucide-react";

/**
 * A ballot that landed on a seat, with the voter's name. A secret vote is dashed, a
 * revealed vote solid, and a ballot on a caught seat takes the imposter colour.
 */
export function BallotChip({
  name,
  revealed,
  caught,
  className,
}: {
  name: string;
  revealed: boolean;
  caught: boolean;
  className?: string;
}) {
  return (
    <span
      data-revealed={revealed}
      data-caught={caught}
      className={cn(
        "flex items-center gap-1 rounded-full border border-dashed border-primary/60 bg-primary/5 px-2 py-0.5 text-xs font-semibold whitespace-nowrap text-primary data-[caught=true]:border-imposter/60 data-[caught=true]:text-imposter data-[revealed=true]:border-solid data-[revealed=true]:border-transparent data-[revealed=true]:bg-primary data-[revealed=true]:text-primary-foreground data-[revealed=true]:data-[caught=true]:bg-imposter",
        className,
      )}
    >
      <Vote className="size-3" />
      {name}
    </span>
  );
}
