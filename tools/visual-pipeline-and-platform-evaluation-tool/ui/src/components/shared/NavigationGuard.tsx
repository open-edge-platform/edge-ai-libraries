import { useCallback, useEffect } from "react";
import { useBlocker } from "react-router";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface NavigationGuardProps {
  when: boolean;
  title?: string;
  description?: string;
  acknowledgeLabel?: string;
}

export const NavigationGuard = ({
  when,
  title = "Job is still running",
  description = "This page is still polling the active job. Stop the job or wait for it to finish before leaving this page.",
  acknowledgeLabel = "OK",
}: NavigationGuardProps) => {
  const blocker = useBlocker(when);

  const resetBlocker = useCallback(() => {
    if (blocker.state === "blocked") {
      blocker.reset?.();
    }
  }, [blocker]);

  useEffect(() => {
    if (!when) {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [when]);

  useEffect(() => {
    if (!when) {
      resetBlocker();
    }
  }, [when, resetBlocker]);

  return (
    <AlertDialog
      open={blocker.state === "blocked"}
      onOpenChange={(open) => {
        if (!open) {
          resetBlocker();
        }
      }}
    >
      <AlertDialogContent className="top-[20%] translate-y-0">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogAction onClick={resetBlocker}>
            {acknowledgeLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};
