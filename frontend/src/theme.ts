import { useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";
export type Theme = "light" | "dark";
const key = "osint-watch-theme";
const preference = (value: string | null | undefined): ThemePreference =>
  value === "light" || value === "dark" ? value : "system";

/** Browser-local preference; unavailable storage never prevents theme changes. */
export function useTheme() {
  const [mode, setMode] = useState<ThemePreference>(() =>
    preference(document.documentElement.dataset.themePreference),
  );
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  useEffect(() => {
    const system = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const resolved =
        mode === "system" ? (system.matches ? "dark" : "light") : mode;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.themePreference = mode;
      setTheme(resolved);
    };
    apply();
    system.addEventListener("change", apply);
    return () => system.removeEventListener("change", apply);
  }, [mode]);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === key || event.key === null)
        setMode(preference(event.newValue));
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  const change = (value: ThemePreference) => {
    setMode(value);
    try {
      localStorage.setItem(key, value);
    } catch {
      /* Remains usable for this session. */
    }
  };
  return { mode, theme, change };
}

/** Only the bundled default basemap is substituted; custom maps stay operator-owned. */
export function themedBasemap(url: string, theme: Theme): string {
  return theme === "dark" &&
    url === "https://tiles.openfreemap.org/styles/liberty"
    ? "https://tiles.openfreemap.org/styles/dark"
    : url;
}
