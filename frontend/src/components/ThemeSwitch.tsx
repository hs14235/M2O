import { useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";
const choices: { value: ThemeChoice; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function savedTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem("m2o-theme");
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(choice: ThemeChoice) {
  if (choice === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  try {
    if (choice === "system") localStorage.removeItem("m2o-theme");
    else localStorage.setItem("m2o-theme", choice);
  } catch {
    /* The choice still applies for this session. */
  }
}

/** Light, Dark or the device setting. public/theme-init.js applies a saved choice before first paint. */
export function ThemeSwitch() {
  const [choice, setChoice] = useState(savedTheme);
  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="inline-flex gap-0.5 rounded-md border border-border bg-surface p-0.5"
    >
      {choices.map((item) => (
        <button
          key={item.value}
          type="button"
          role="radio"
          aria-checked={choice === item.value}
          onClick={() => {
            const change = () => {
              applyTheme(item.value);
              setChoice(item.value);
            };
            // Cross-fade the whole page unless motion is turned off.
            if (document.startViewTransition && document.documentElement.dataset.motion !== "calm")
              document.startViewTransition(change);
            else change();
          }}
          className={
            "min-h-9 rounded-sm border-0 px-3 text-sm font-medium " +
            (choice === item.value
              ? "bg-surface-2 text-text shadow-[0_0_0_1px_var(--border)]"
              : "bg-transparent text-text-2")
          }
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
