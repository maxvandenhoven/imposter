import { Play } from "lucide-react";
import { useState } from "react";

import { useCatalog } from "@/api/catalog";
import type { CatalogResponse, GameRequest } from "@/api/types";
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
              Seats are shuffled and the imposters are picked at random, unless you choose
              them with the mask.
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

/** The setup view: loads the catalog and shows the setup form. */
export function SetupPage({ onStart }: { onStart: (request: GameRequest) => void }) {
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

  return <SetupForm catalog={catalog.data} onStart={onStart} />;
}
