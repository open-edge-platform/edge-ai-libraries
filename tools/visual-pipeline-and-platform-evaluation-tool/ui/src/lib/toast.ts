import { toast as sonnerToast } from "sonner";

const toast = {
  ...sonnerToast,
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
};

export { toast };
