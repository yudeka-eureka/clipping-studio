import { cn } from "@/lib/utils";

/** Pill switch used across the studio screens (violet track with a check knob). */
export function Toggle({
  checked,
  onChange,
  label,
  size = "md",
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  size?: "sm" | "md";
}) {
  const sm = size === "sm";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "shrink-0 rounded-full p-1 flex items-center shadow-inner transition-colors",
        sm ? "w-10 h-6" : "w-12 h-7",
        checked ? "bg-primary" : "bg-surface-container-highest",
      )}
    >
      <span
        className={cn(
          "rounded-full bg-surface-container-lowest shadow-xs flex items-center justify-center transition-transform",
          sm ? "w-4 h-4" : "w-5 h-5",
          checked ? (sm ? "translate-x-4" : "translate-x-5") : "translate-x-0",
        )}
      >
        <span
          className={cn(
            "material-symbols-outlined",
            sm ? "text-[10px]" : "text-[12px]",
            checked ? "text-primary" : "text-outline",
          )}
          style={{ fontVariationSettings: "'FILL' 1" }}
        >
          {checked ? "check" : "remove"}
        </span>
      </span>
    </button>
  );
}
