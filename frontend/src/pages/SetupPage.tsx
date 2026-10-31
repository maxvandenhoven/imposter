import { CircleAlert, Eye, Play, SlidersHorizontal, Upload, Users } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";

import { useCatalog } from "@/api/catalog";
import type { CatalogResponse, GameEvent, GameRequest } from "@/api/types";
import { NumberedSection, SectionPanel } from "@/components/NumberedSection";
import { HowToPlay } from "@/components/rules/HowToPlay";
import { AdvancedOptions } from "@/components/setup/AdvancedOptions";
import { IdentityModeField } from "@/components/setup/IdentityModeField";
import { OptionSwitch } from "@/components/setup/OptionSwitch";
import { SeatList } from "@/components/setup/SeatList";
import { WordOptions } from "@/components/setup/WordOptions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { parseGameExport } from "@/lib/gameExport";
import {
  defaultSetupForm,
  gameRequest,
  type SetupForm as SetupFormState,
  type SetupProblem,
  setupProblems,
  type SetupSection,
} from "@/lib/setup";

/** The problems of one section of the setup form, shown where they are fixed. */
function SectionProblems({
  problems,
  section,
}: {
  problems: SetupProblem[];
  section: SetupSection;
}) {
  const messages = problems
    .filter((problem) => problem.section === section)
    .map((problem) => problem.message);

  if (messages.length === 0) {
    return null;
  }

  return (
    <Alert variant="destructive">
      <CircleAlert />
      <AlertTitle>
        {messages.length === 1 ? messages[0] : "Fix these to start"}
      </AlertTitle>
      {messages.length > 1 && (
        <AlertDescription>
          <ul className="list-inside list-disc">
            {messages.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </AlertDescription>
      )}
    </Alert>
  );
}

/** The setup form, once the catalog is known, with `actions` beside the start button. */
export function SetupForm({
  catalog,
  onStart,
  actions,
}: {
  catalog: CatalogResponse;
  onStart: (request: GameRequest) => void;
  actions?: ReactNode;
}) {
  const [form, setForm] = useState(() => defaultSetupForm(catalog));
  const problems = setupProblems(form);

  const update = (patch: Partial<SetupFormState>) => {
    setForm((current) => ({ ...current, ...patch }));
  };

  return (
    // The limits are checked by `setupProblems`, not by the browser's own validation.
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();

        if (problems.length === 0) {
          onStart(gameRequest(form, catalog.models));
        }
      }}
    >
      <SectionPanel>
        <NumberedSection
          id="setup-word"
          icon={Eye}
          step={1}
          title="Secret word"
          intro={
            <p>
              Choose how the secret word is picked. Every civilian is told the word, while
              the imposters have to work it out from the clues.
            </p>
          }
        >
          <WordOptions form={form} categories={catalog.categories} onChange={update} />
          <SectionProblems problems={problems} section="word" />
        </NumberedSection>
        <NumberedSection
          id="setup-players"
          icon={Users}
          step={2}
          title="Players"
          intro={
            <p>
              Pick a model for each seat and mark the imposters with the mask. Drag a seat
              by its handle to move it. The seats are shuffled when the game starts, so
              the order here does not decide who goes first.
            </p>
          }
        >
          <SeatList
            seats={form.seats}
            models={catalog.models}
            onChange={(seats) => {
              update({ seats });
            }}
          />
          <SectionProblems problems={problems} section="players" />
        </NumberedSection>
        <NumberedSection
          id="setup-rules"
          icon={SlidersHorizontal}
          step={3}
          title="Rules"
          intro={
            <p>
              Decide what the players know about each other and about the word. The
              defaults suit most games, and Advanced sets the length and limits.
            </p>
          }
        >
          <IdentityModeField
            value={form.identityMode}
            onChange={(identityMode) => {
              update({ identityMode });
            }}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <OptionSwitch
              id="public-category"
              label="Public category"
              description="Every player, the imposters too, is told the category of the word. This gives the imposters a head start, so they are harder to catch."
              checked={form.publicCategory}
              onChange={(publicCategory) => {
                update({ publicCategory });
              }}
            />
            <OptionSwitch
              id="imposter-hint"
              label="Imposter hint"
              description="Gemini 3.5 Flash-Lite generates one related word that does not give the secret word away, and the imposters get it at the start. This makes them harder to catch."
              checked={form.imposterHint}
              onChange={(imposterHint) => {
                update({ imposterHint });
              }}
            />
          </div>
          <AdvancedOptions form={form} onChange={update} />
          <SectionProblems problems={problems} section="rules" />
        </NumberedSection>
      </SectionPanel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        {actions}
        {problems.length > 0 && (
          <p className="ml-auto self-center text-sm text-destructive">
            Fix the marked sections to start the game.
          </p>
        )}
        <Button
          type="submit"
          size="lg"
          className="ml-auto"
          disabled={problems.length > 0}
        >
          <Play data-icon="inline-start" />
          Start game
        </Button>
      </div>
    </form>
  );
}

/** A game that was read from an export file. */
export interface ImportedGame {
  config: GameRequest;
  events: GameEvent[];
}

/** Import an exported game from a file, to replay it without a backend game. */
function ImportGame({ onImport }: { onImport: (game: ImportedGame) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const read = async (file: File) => {
    try {
      onImport(parseGameExport(await file.text()));
      setProblem(null);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The file could not be read.");
    }
  };

  return (
    <div className="flex flex-col items-start gap-2">
      <input
        ref={input}
        type="file"
        accept="application/json,.json"
        aria-label="Exported game"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";

          if (file !== undefined) {
            void read(file);
          }
        }}
      />
      <Button
        variant="outline"
        size="lg"
        onClick={() => {
          input.current?.click();
        }}
      >
        <Upload data-icon="inline-start" />
        Import a game
      </Button>
      {problem !== null && (
        <Alert variant="destructive">
          <AlertTitle>The game could not be imported</AlertTitle>
          <AlertDescription>{problem}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}

/**
 * The setup view: loads the catalog and shows the setup form, with a way to import, and
 * the rules of the game below it.
 */
export function SetupPage({
  onStart,
  onImport,
}: {
  onStart: (request: GameRequest) => void;
  onImport: (game: ImportedGame) => void;
}) {
  const catalog = useCatalog();

  if (catalog.isPending) {
    return <p className="text-muted-foreground">Loading the models and categories…</p>;
  }

  if (catalog.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>The catalog could not be loaded</AlertTitle>
        <AlertDescription>{catalog.error.message}</AlertDescription>
      </Alert>
    );
  }

  return (
    <>
      <SetupForm
        catalog={catalog.data}
        onStart={onStart}
        actions={<ImportGame onImport={onImport} />}
      />
      <HowToPlay />
    </>
  );
}
