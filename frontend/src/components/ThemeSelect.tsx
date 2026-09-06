import type { ThemePreference } from "../theme";
export default function ThemeSelect({
  value,
  onChange,
}: {
  value: ThemePreference;
  onChange: (value: ThemePreference) => void;
}) {
  return (
    <label className="filter-label theme-select">
      Appearance
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as ThemePreference)}
      >
        <option value="system">System theme</option>
        <option value="light">Light theme</option>
        <option value="dark">Dark theme</option>
      </select>
    </label>
  );
}
