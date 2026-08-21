import { PILOT_CITIES } from "@/lib/copy";

export function CityField({
  name,
  value,
  defaultValue = "Москва",
  onChange,
}: {
  name?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
}) {
  return (
    <label>
      Город
      <input
        name={name}
        list="booker-cities"
        autoComplete="address-level2"
        {...(onChange
          ? { value: value ?? "", onChange: (e) => onChange(e.target.value) }
          : { defaultValue })}
      />
      <datalist id="booker-cities">
        {PILOT_CITIES.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
    </label>
  );
}
