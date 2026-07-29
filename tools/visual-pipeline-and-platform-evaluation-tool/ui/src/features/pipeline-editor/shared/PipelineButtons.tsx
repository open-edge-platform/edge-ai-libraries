// SPDX-License-Identifier: Apache-2.0
import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type PipelineToolbarButtonVariant = ComponentProps<
  typeof Button
>["variant"];

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

export const PipelineToolbarButton = ({
  onClick,
  disabled,
  title,
  icon,
  label,
  variant = "default",
  widthClassName,
  className,
}: PipelineToolbarButtonProps) => (
  <Button
    onClick={onClick}
    disabled={disabled}
    title={title}
    type="button"
    variant={variant}
    className={cn(
      "px-3 py-2 h-auto shadow-lg gap-2 font-medium text-[1.025rem]",
      widthClassName,
      className,
    )}
  >
    {icon}
    {label}
  </Button>
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
  <Button
    onClick={onClick}
    disabled={disabled}
    type="button"
    className={cn(
      "w-full h-auto text-left px-3 py-2 rounded hover:bg-muted transition-colors text-[1.025rem] flex items-start gap-2",
      className,
    )}
  >
    {icon}
    <div>
      <div className="font-medium">{title}</div>
      <div className="text-xs text-muted-foreground">{description}</div>
    </div>
  </Button>
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
  <Button
    onClick={onClick}
    disabled={disabled}
    type="button"
    className={cn(
      "px-4 py-2 h-auto text-[1.025rem] font-medium transition-colors disabled:cursor-not-allowed",
      DIALOG_VARIANT_CLASSES[variant],
      className,
    )}
  >
    {children}
  </Button>
);
