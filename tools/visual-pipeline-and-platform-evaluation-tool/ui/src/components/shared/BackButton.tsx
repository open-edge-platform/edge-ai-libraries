import { ArrowLeft } from "lucide-react";
import { Link, type LinkProps } from "react-router";
import { cn } from "@/lib/utils";

type BackButtonProps = Omit<LinkProps, "to" | "children"> & {
  to: LinkProps["to"];
  iconClassName?: string;
};

export const BackButton = ({
  to,
  className,
  iconClassName,
  ...rest
}: BackButtonProps) => {
  return (
    <Link
      to={to}
      className={cn(
        "size-8 flex items-center justify-center hover:bg-accent dark:hover:bg-accent/50 transition-colors",
        className,
      )}
      {...rest}
    >
      <ArrowLeft className={cn("h-5 w-5", iconClassName)} />
    </Link>
  );
};
