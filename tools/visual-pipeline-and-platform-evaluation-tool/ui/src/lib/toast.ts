import { toast as sonnerToast } from "sonner";

const toast = {
  success: sonnerToast.success,
  info: sonnerToast.info,
  warning: (
    message: Parameters<typeof sonnerToast.warning>[0],
    data?: Parameters<typeof sonnerToast.warning>[1],
  ) =>
    sonnerToast.warning(message, {
      ...data,
      closeButton: true,
      duration: Infinity,
      dismissible: true,
    }),
  error: (
    message: Parameters<typeof sonnerToast.error>[0],
    data?: Parameters<typeof sonnerToast.error>[1],
  ) =>
    sonnerToast.error(message, {
      ...data,
      closeButton: true,
      duration: Infinity,
      dismissible: true,
    }),
  custom: sonnerToast.custom,
  message: sonnerToast.message,
  promise: sonnerToast.promise,
  dismiss: sonnerToast.dismiss,
  loading: sonnerToast.loading,
  getHistory: sonnerToast.getHistory,
  getToasts: sonnerToast.getToasts,
};

export { toast };