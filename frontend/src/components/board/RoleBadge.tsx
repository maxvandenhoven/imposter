import { ShieldCheck, VenetianMask } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { SeatRole } from "@/lib/boardView";

/** The role of a seat, as a badge in the role's colour. */
export function RoleBadge({ role }: { role: SeatRole }) {
  if (role === "imposter") {
    return (
      <Badge className="bg-imposter text-white">
        <VenetianMask data-icon="inline-start" />
        Imposter
      </Badge>
    );
  }

  return (
    <Badge className="bg-civilian/12 text-civilian">
      <ShieldCheck data-icon="inline-start" />
      Civilian
    </Badge>
  );
}
