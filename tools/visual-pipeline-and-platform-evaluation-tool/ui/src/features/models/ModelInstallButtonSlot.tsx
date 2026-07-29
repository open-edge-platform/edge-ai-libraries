import { Button } from "@/components/ui/button.tsx";
import { Download } from "lucide-react";

type ModelInstallButtonSlotProps = {
  showButton: boolean;
  onInstall?: () => void | Promise<void>;
  disabled?: boolean;
  className?: string;
};

export const ModelInstallButtonSlot = ({
  showButton,
  onInstall,
  disabled = false,
  className,
}: ModelInstallButtonSlotProps) => {
  const slotClassName = className
    ? `flex min-h-9 min-w-[96px] items-center justify-end ${className}`
    : "flex min-h-9 min-w-[96px] items-center justify-end";

  return (
    <div className={slotClassName}>
      {showButton && onInstall ? (
        <Button
          size="sm"
          variant="outline"
          disabled={disabled}
          onClick={onInstall}
        >
          <Download className="size-4" />
          Install
        </Button>
      ) : (
        <span className="h-9" aria-hidden="true" />
      )}
    </div>
  );
};
