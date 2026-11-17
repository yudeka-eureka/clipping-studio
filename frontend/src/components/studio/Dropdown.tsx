import * as SelectPrimitive from "@radix-ui/react-select";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export type DropdownOption<T extends string = string> = {
  value: T;
  label: string;
  description?: string;
  icon?: string;
};

type DropdownProps<T extends string> = {
  options: readonly DropdownOption<T>[];
  value?: T;
  defaultValue?: T;
  onValueChange?: (value: T) => void;
  /** Leading Material Symbol shown inside the trigger. */
  icon?: string;
  iconClassName?: string;
  id?: string;
  "aria-label"?: string;
  disabled?: boolean;
  /** Trigger surface: "lowest" sits on tinted cards, "container" on light ones. */
  tone?: "lowest" | "container";
  size?: "sm" | "md";
  className?: string;
  /** Custom trigger content for the selected option (e.g. a preview badge). */
  renderValue?: (option: DropdownOption<T>) => ReactNode;
};

/** Studio dropdown: themed trigger + floating menu with check marks and optional descriptions. */
export function Dropdown<T extends string>({
  options,
  value,
  defaultValue,
  onValueChange,
  icon,
  iconClassName,
  id,
  disabled,
  tone = "lowest",
  size = "sm",
  className,
  renderValue,
  ...rest
}: DropdownProps<T>) {
  const [inner, setInner] = useState<T | undefined>(defaultValue ?? options[0]?.value);
  const current = value ?? inner;
  const selected = options.find((o) => o.value === current) ?? options[0];

  return (
    <SelectPrimitive.Root
      {...(current !== undefined ? { value: current } : {})}
      disabled={disabled ?? false}
      onValueChange={(v) => {
        setInner(v as T);
        onValueChange?.(v as T);
      }}
    >
      <SelectPrimitive.Trigger
        {...(id ? { id } : {})}
        {...(rest["aria-label"] ? { "aria-label": rest["aria-label"] } : {})}
        className={cn(
          "group relative flex w-full min-w-0 items-center gap-2 rounded-lg px-space-sm text-left text-on-surface outline-hidden transition-colors",
          "focus-visible:ring-2 focus-visible:ring-primary data-[state=open]:ring-2 data-[state=open]:ring-primary",
          "disabled:cursor-not-allowed disabled:opacity-60",
          tone === "lowest"
            ? "bg-surface-container-lowest hover:bg-surface-container-low"
            : "bg-surface-container hover:bg-surface-container-high",
          size === "sm"
            ? "min-h-10 py-2 font-body-sm text-body-sm"
            : "min-h-11 py-2.5 font-body-md text-body-md",
          className,
        )}
      >
        {icon && (
          <span
            className={cn(
              "material-symbols-outlined shrink-0 text-[18px] text-outline",
              iconClassName,
            )}
          >
            {icon}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">
          <SelectPrimitive.Value>
            {selected && (renderValue ? renderValue(selected) : selected.label)}
          </SelectPrimitive.Value>
        </span>
        <SelectPrimitive.Icon asChild>
          <span className="material-symbols-outlined shrink-0 text-[20px] text-outline transition-transform duration-200 group-data-[state=open]:rotate-180">
            expand_more
          </span>
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={6}
          collisionPadding={12}
          className={cn(
            "z-50 min-w-(--radix-select-trigger-width) max-h-(--radix-select-content-available-height) overflow-hidden rounded-xl",
            "bg-surface-container-lowest text-on-surface shadow-lg ring-1 ring-outline-variant/50",
            "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2",
            "origin-(--radix-select-content-transform-origin)",
          )}
        >
          <SelectPrimitive.Viewport className="flex flex-col gap-0.5 p-1.5">
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                value={o.value}
                className={cn(
                  "relative flex cursor-pointer select-none items-center gap-2.5 rounded-lg py-2 pl-2.5 pr-9 outline-hidden transition-colors",
                  "data-highlighted:bg-surface-container data-[state=checked]:bg-secondary-container data-[state=checked]:text-on-surface",
                  "data-disabled:pointer-events-none data-disabled:opacity-50",
                )}
              >
                {o.icon && (
                  <span className="material-symbols-outlined shrink-0 text-[18px] text-primary">
                    {o.icon}
                  </span>
                )}
                <span className="flex min-w-0 flex-col">
                  <SelectPrimitive.ItemText>
                    <span className="font-label-lg text-label-lg font-medium">{o.label}</span>
                  </SelectPrimitive.ItemText>
                  {o.description && (
                    <span className="font-body-sm text-body-sm text-on-surface-variant">
                      {o.description}
                    </span>
                  )}
                </span>
                <SelectPrimitive.ItemIndicator className="absolute right-2.5 flex items-center">
                  <span className="material-symbols-outlined text-[18px] text-primary">check</span>
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
