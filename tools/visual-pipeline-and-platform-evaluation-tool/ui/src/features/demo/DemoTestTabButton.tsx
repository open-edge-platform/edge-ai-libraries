// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type DemoTestTabButtonProps = {
  isActive: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
};

export const DemoTestTabButton = ({
  isActive,
  disabled,
  onClick,
  children,
}: DemoTestTabButtonProps) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={cn(
      "px-3 py-1.5 text-xs font-semibold rounded-md transition-all disabled:opacity-50 disabled:cursor-not-allowed",
      isActive
        ? "bg-demo-checkbox-active text-white"
        : "text-demo-panel-title hover:text-primary-foreground",
    )}
  >
    {children}
  </button>
);
