import { useWebSocketConnection } from "@/hooks/useWebSocketConnection.ts";
import type { ReactNode } from "react";

interface MetricsProviderProps {
  children: ReactNode;
}

export const MetricsProvider = ({ children }: MetricsProviderProps) => {
  useWebSocketConnection();

  return <>{children}</>;
};
