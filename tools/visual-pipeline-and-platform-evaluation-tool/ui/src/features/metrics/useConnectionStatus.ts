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
    if (isConnected) return "status-success text-status-fg";
    if (isConnecting) return "status-accent text-status-fg";
    return "status-error text-status-fg";
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
