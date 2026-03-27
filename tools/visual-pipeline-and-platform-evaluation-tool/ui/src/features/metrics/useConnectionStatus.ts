import { useAppSelector } from "@/store/hooks.ts";
import {
  selectError,
  selectIsConnected,
  selectIsConnecting,
} from "@/store/reducers/metrics.ts";

export const useConnectionStatus = () => {
  const isConnected = useAppSelector(selectIsConnected);
  const isConnecting = useAppSelector(selectIsConnecting);
  const error = useAppSelector(selectError);

  const getStatusColor = () => {
    if (isConnected) return "text-status-success-fg";
    if (isConnecting) return "text-status-accent-fg";
    return "text-status-error-fg";
  };

  const getStatusIcon = () => (isConnected ? "●" : "○");

  return {
    isConnected,
    isConnecting,
    error,
    statusColor: getStatusColor(),
    statusIcon: getStatusIcon(),
  };
};
