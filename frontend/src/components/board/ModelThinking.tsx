import { ChevronRight, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

/** The model's native thinking, collapsed until opened, which only god mode shows. */
export function ModelThinking({ text }: { text: string }) {
  return (
    <Collapsible className="group/thinking">
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="xs" className="text-muted-foreground">
          <ChevronRight className="transition-transform group-data-[state=open]/thinking:rotate-90" />
          <Sparkles />
          Model thinking
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p className="mt-1 max-h-40 overflow-y-auto rounded-lg bg-muted px-3 py-2 font-mono text-xs whitespace-pre-wrap text-muted-foreground">
          {text}
        </p>
      </CollapsibleContent>
    </Collapsible>
  );
}
