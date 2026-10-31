import type { IdentityMode } from "@/api/types";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

const IDENTITY_MODES: { mode: IdentityMode; label: string; description: string }[] = [
  { mode: "seat", label: "Seats", description: "Players are Player 1 to Player N." },
  {
    mode: "names",
    label: "Names",
    description: "Players are Alice, Bob, Charlie and so on.",
  },
  {
    mode: "models",
    label: "Models",
    description: "Players are named after their models, so they know who is who.",
  },
];

/** How players are named, which decides whether they know each other's models. */
export function IdentityModeField({
  value,
  onChange,
}: {
  value: IdentityMode;
  onChange: (mode: IdentityMode) => void;
}) {
  const description = IDENTITY_MODES.find((option) => option.mode === value)?.description;

  return (
    <Field>
      <FieldLabel id="identity-mode-label">Identity</FieldLabel>
      <ToggleGroup
        type="single"
        variant="outline"
        aria-labelledby="identity-mode-label"
        value={value}
        onValueChange={(mode) => {
          // A click on the pressed item clears the value, which keeps the mode.
          if (mode !== "") {
            onChange(mode as IdentityMode);
          }
        }}
      >
        {IDENTITY_MODES.map((option) => (
          <ToggleGroupItem key={option.mode} value={option.mode}>
            {option.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <FieldDescription>{description}</FieldDescription>
    </Field>
  );
}
