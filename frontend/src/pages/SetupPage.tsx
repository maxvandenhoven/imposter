import { Play, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { useCatalog } from "@/api/catalog";
import type { CatalogResponse, GameEvent, GameRequest } from "@/api/types";
import { AdvancedOptions } from "@/components/setup/AdvancedOptions";
import { IdentityModeField } from "@/components/setup/IdentityModeField";
import { OptionSwitch } from "@/components/setup/OptionSwitch";
import { SeatList } from "@/components/setup/SeatList";
import { WordOptions } from "@/components/setup/WordOptions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { parseGameExport } from "@/lib/gameExport";
import {
  defaultSetupForm,
  gameRequest,
  type SetupForm as SetupFormState,
  setupProblems,
} from "@/lib/setup";

/** The setup form, once the catalog is known. */
export function SetupForm({
  catalog,
  onStart,
}: {
  catalog: CatalogResponse;
  onStart: (request: GameRequest) => void;
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
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();

        if (problems.length === 0) {
          onStart(gameRequest(form, catalog.models));
        }
      }}
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Secret word</CardTitle>
            <CardDescription>Civilians learn it, the imposter does not.</CardDescription>
          </CardHeader>
          <CardContent>
            <WordOptions form={form} categories={catalog.categories} onChange={update} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Players</CardTitle>
            <CardDescription>
              Seats are shuffled before the game starts. The players with the mask are the
              imposters.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SeatList
              seats={form.seats}
              models={catalog.models}
              onChange={(seats) => {
                update({ seats });
              }}
            />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Rules</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
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
              description="Everyone, the imposter too, learns the category of the word."
              checked={form.publicCategory}
              onChange={(publicCategory) => {
                update({ publicCategory });
              }}
            />
            <OptionSwitch
              id="imposter-hint"
              label="Imposter hint"
              description="The imposter gets a related word as a hint."
              checked={form.imposterHint}
              onChange={(imposterHint) => {
                update({ imposterHint });
              }}
            />
          </div>
          <AdvancedOptions form={form} onChange={update} />
        </CardContent>
      </Card>
      {problems.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>The game cannot start yet</AlertTitle>
          <AlertDescription>
            <ul className="list-inside list-disc">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      <Button type="submit" size="lg" className="self-end" disabled={problems.length > 0}>
        <Play data-icon="inline-start" />
        Start game
      </Button>
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
    <div className="flex flex-col items-end gap-2">
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

/** The setup view: loads the catalog and shows the setup form, with a way to import. */
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
      <ImportGame onImport={onImport} />
      <SetupForm catalog={catalog.data} onStart={onStart} />
    </>
  );
}
