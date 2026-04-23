import { useContext } from "react";
import { BackgroundJobsContext } from "./BackgroundJobsContext";

export const useBackgroundJobs = () => {
  const context = useContext(BackgroundJobsContext);
  if (!context) {
    throw new Error(
      "useBackgroundJobs must be used within BackgroundJobsProvider",
    );
  }
  return context;
};
