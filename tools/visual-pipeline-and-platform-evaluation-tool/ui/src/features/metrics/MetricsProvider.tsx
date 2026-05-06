import { useMetricsStream } from "@/hooks/useMetricsStream.ts";
import type { ReactNode } from "react";

interface MetricsProviderProps {
  children: ReactNode;
}

export const MetricsProvider = ({ children }: MetricsProviderProps) => {
  useMetricsStream();

  return <>{children}</>;
};
