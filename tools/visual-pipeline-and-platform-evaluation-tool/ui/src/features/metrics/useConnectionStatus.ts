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
    if (isConnected) return "text-green-600";
    if (isConnecting) return "text-yellow-600";
    return "text-red-600";
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
