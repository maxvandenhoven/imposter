import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

/** A number input. An empty input gives `NaN`, which the limits then report. */
export function NumberField({
  id,
  label,
  description,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  id: string;
  label: string;
  description?: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        step={step}
        value={Number.isNaN(value) ? "" : value}
        onChange={(event) => {
          const text = event.target.value;
          onChange(text === "" ? Number.NaN : Number(text));
        }}
      />
      {description !== undefined && <FieldDescription>{description}</FieldDescription>}
    </Field>
  );
}
