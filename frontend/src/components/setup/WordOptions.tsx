import type { CatalogCategory, WordMode } from "@/api/types";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ANY_CATEGORY, type SetupForm } from "@/lib/setup";

/** Radix selects cannot hold an empty value, so "any category" has its own. */
const ANY_CATEGORY_ITEM = "any";

function CategorySelect({
  categories,
  value,
  onChange,
  anyLabel,
}: {
  categories: CatalogCategory[];
  value: string;
  onChange: (category: string) => void;
  anyLabel: string;
}) {
  const selected = value === ANY_CATEGORY ? ANY_CATEGORY_ITEM : value;
  const description = categories.find((category) => category.name === value)?.description;

  return (
    <Field>
      <FieldLabel htmlFor="category">Category</FieldLabel>
      <Select
        value={selected}
        onValueChange={(item) => {
          onChange(item === ANY_CATEGORY_ITEM ? ANY_CATEGORY : item);
        }}
      >
        <SelectTrigger id="category" className="w-full sm:w-72">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY_CATEGORY_ITEM}>{anyLabel}</SelectItem>
          {categories.map((category) => (
            <SelectItem key={category.name} value={category.name}>
              {category.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {description !== undefined && <FieldDescription>{description}</FieldDescription>}
    </Field>
  );
}

/** How the secret word is chosen: from a category, typed, or generated. */
export function WordOptions({
  form,
  categories,
  onChange,
}: {
  form: SetupForm;
  categories: CatalogCategory[];
  onChange: (patch: Partial<SetupForm>) => void;
}) {
  const setCategory = (category: string) => {
    onChange({ category });
  };

  return (
    <Tabs
      value={form.wordMode}
      onValueChange={(mode) => {
        onChange({ wordMode: mode as WordMode });
      }}
    >
      <TabsList>
        <TabsTrigger value="random">Random</TabsTrigger>
        <TabsTrigger value="typed">Type</TabsTrigger>
        <TabsTrigger value="generated">Surprise me</TabsTrigger>
      </TabsList>
      <TabsContent value="random" className="pt-3">
        <CategorySelect
          categories={categories}
          value={form.category}
          onChange={setCategory}
          anyLabel="Any category"
        />
      </TabsContent>
      <TabsContent value="typed" className="flex flex-col gap-4 pt-3">
        <Field>
          <FieldLabel htmlFor="secret-word">Secret word</FieldLabel>
          <Input
            id="secret-word"
            className="sm:w-72"
            autoComplete="off"
            placeholder="lighthouse"
            value={form.word}
            onChange={(event) => {
              onChange({ word: event.target.value });
            }}
          />
        </Field>
        <CategorySelect
          categories={categories}
          value={form.category}
          onChange={setCategory}
          anyLabel="No category"
        />
      </TabsContent>
      <TabsContent value="generated" className="pt-3">
        <p className="text-sm text-muted-foreground">
          Gemini makes up a fresh word and its category when the game starts.
        </p>
      </TabsContent>
    </Tabs>
  );
}
