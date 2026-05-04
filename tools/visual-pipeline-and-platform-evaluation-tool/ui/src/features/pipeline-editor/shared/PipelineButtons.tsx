// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type PipelineToolbarButtonVariant =
  | "primary"
  | "accent-outline"
  | "destructive"
  | "icon-primary";

export type PipelineToolbarButtonProps = {
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
  icon?: ReactNode;
  label?: ReactNode;
  variant?: PipelineToolbarButtonVariant;
  widthClassName?: string;
  className?: string;
};

const TOOLBAR_VARIANT_CLASSES: Record<PipelineToolbarButtonVariant, string> = {
  primary:
    "bg-primary hover:bg-primary/90 text-primary-foreground disabled:bg-muted rounded-none",
  "accent-outline":
    "bg-background hover:bg-brand-accent text-brand-accent hover:text-white border-2 border-brand-accent rounded-none",
  destructive:
    "bg-destructive hover:bg-destructive/90 text-primary-foreground disabled:bg-destructive/40 rounded-none",
  "icon-primary":
    "bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg",
};

export const PipelineToolbarButton = ({
  onClick,
  disabled,
  title,
  icon,
  label,
  variant = "primary",
  widthClassName,
  className,
}: PipelineToolbarButtonProps) => (
  <button
    onClick={onClick}
    disabled={disabled}
    title={title}
    className={cn(
      "px-3 py-2 shadow-lg transition-colors flex items-center gap-2 font-medium disabled:opacity-50",
      TOOLBAR_VARIANT_CLASSES[variant],
      widthClassName,
      className,
    )}
  >
    {icon}
    {label}
  </button>
);

export type PipelineMenuOptionButtonProps = {
  onClick?: () => void;
  disabled?: boolean;
  icon: ReactNode;
  title: ReactNode;
  description: ReactNode;
  className?: string;
};

export const PipelineMenuOptionButton = ({
  onClick,
  disabled,
  icon,
  title,
  description,
  className,
}: PipelineMenuOptionButtonProps) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={cn(
      "w-full text-left px-3 py-2 rounded hover:bg-muted transition-colors text-sm disabled:opacity-50 flex items-start gap-2",
      className,
    )}
  >
    {icon}
    <div>
      <div className="font-medium">{title}</div>
      <div className="text-xs text-muted-foreground">{description}</div>
    </div>
  </button>
);

export type PipelineDialogButtonVariant = "primary" | "secondary";

export type PipelineDialogButtonProps = {
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
  variant?: PipelineDialogButtonVariant;
  className?: string;
};

const DIALOG_VARIANT_CLASSES: Record<PipelineDialogButtonVariant, string> = {
  primary: "text-primary-foreground bg-primary rounded-md hover:bg-primary/90",
  secondary:
    "text-foreground bg-background border border-input rounded-md hover:bg-muted",
};

export const PipelineDialogButton = ({
  onClick,
  disabled,
  children,
  variant = "secondary",
  className,
}: PipelineDialogButtonProps) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={cn(
      "px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
      DIALOG_VARIANT_CLASSES[variant],
      className,
    )}
  >
    {children}
  </button>
);
