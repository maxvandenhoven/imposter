import { LoaderCircle } from "lucide-react";

import type { PartialAnswer } from "@/api/gameStream";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** The answer a seat is writing: the model's thinking, then the answer text. */
function AnswerText({ answer }: { answer: PartialAnswer }) {
  return (
    <div className="flex flex-col gap-1 font-mono text-xs break-words whitespace-pre-wrap">
      {answer.thought !== "" && (
        <p className="text-muted-foreground italic" data-testid="answer-thought">
          {answer.thought}
        </p>
      )}
      {answer.text !== "" && <p data-testid="answer-text">{answer.text}</p>}
    </div>
  );
}

/** The seats of the game, with a thinking marker and the answer of each speaking seat. */
export function SeatList({
  names,
  thinking,
  answers,
}: {
  names: Map<number, string>;
  thinking: number[];
  answers: Partial<Record<number, PartialAnswer>>;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {[...names].map(([seat, name]) => {
        const isThinking = thinking.includes(seat);
        const answer = answers[seat];

        return (
          <Card
            key={seat}
            size="sm"
            data-thinking={isThinking}
            className="transition-shadow data-[thinking=true]:ring-2 data-[thinking=true]:ring-speaking"
          >
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {name}
                {isThinking && (
                  <Badge variant="outline" className="gap-1 text-speaking">
                    <LoaderCircle className="animate-spin" />
                    thinking
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            {isThinking && answer !== undefined && (
              <CardContent>
                <AnswerText answer={answer} />
              </CardContent>
            )}
          </Card>
        );
      })}
    </div>
  );
}
