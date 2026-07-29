import { type ModelInstallStatus } from "@/api/api.generated.ts";
import { Badge } from "@/components/ui/badge.tsx";
import { Loader2 } from "lucide-react";

type ModelInstallStatusIndicatorProps = {
  status: ModelInstallStatus;
  showInstalling?: boolean;
};

const formatInstallStatus = (status: ModelInstallStatus): string =>
  status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

const STATUS_BADGE_VARIANT: Record<
  ModelInstallStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  installed: "default",
  installing: "secondary",
  not_installed: "outline",
  failed: "destructive",
};

export const ModelInstallStatusIndicator = ({
  status,
  showInstalling = false,
}: ModelInstallStatusIndicatorProps) => {
  if (showInstalling || status === "installing") {
    return (
      <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        Installing
      </span>
    );
  }

  return (
    <Badge variant={STATUS_BADGE_VARIANT[status]}>
      {formatInstallStatus(status)}
    </Badge>
  );
};
