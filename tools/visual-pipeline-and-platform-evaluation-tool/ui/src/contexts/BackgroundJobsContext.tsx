import { createContext, useState, useCallback } from "react";
import type { ReactNode } from "react";

export type Job = {
  id: string;
  name: string;
  progress: number; // 0-100, jobs with 0 < progress < 100 are considered active
};

export type JobGroup = {
  id: string;
  name: string;
  jobs: Job[];
  hideOnRoutes?: string[];
};

type BackgroundJobsContextType = {
  jobGroups: Map<string, JobGroup>;
  registerJobGroup: (
    groupId: string,
    name: string,
    hideOnRoutes?: string[],
  ) => void;
  unregisterJobGroup: (groupId: string) => void;
  updateJobs: (groupId: string, jobs: Job[]) => void;
  getVisibleJobGroups: (currentRoute: string) => JobGroup[];
  hasActiveJobs: boolean;
};

const BackgroundJobsContext = createContext<
  BackgroundJobsContextType | undefined
>(undefined);

export { BackgroundJobsContext };

export const BackgroundJobsProvider = ({
  children,
}: {
  children: ReactNode;
}) => {
  const [jobGroups, setJobGroups] = useState<Map<string, JobGroup>>(new Map());

  const registerJobGroup = useCallback(
    (groupId: string, name: string, hideOnRoutes?: string[]) => {
      setJobGroups((prev) => {
        const newGroups = new Map(prev);
        if (!newGroups.has(groupId)) {
          newGroups.set(groupId, {
            id: groupId,
            name,
            jobs: [],
            hideOnRoutes,
          });
        }
        return newGroups;
      });
    },
    [],
  );

  const unregisterJobGroup = useCallback((groupId: string) => {
    setJobGroups((prev) => {
      const newGroups = new Map(prev);
      newGroups.delete(groupId);
      return newGroups;
    });
  }, []);

  const updateJobs = useCallback((groupId: string, jobs: Job[]) => {
    setJobGroups((prev) => {
      const newGroups = new Map(prev);
      const group = newGroups.get(groupId);
      if (group) {
        newGroups.set(groupId, {
          ...group,
          jobs,
        });
      }
      return newGroups;
    });
  }, []);

  const getVisibleJobGroups = useCallback(
    (currentRoute: string): JobGroup[] => {
      return Array.from(jobGroups.values())
        .filter((group) => {
          if (!group.hideOnRoutes || group.hideOnRoutes.length === 0) {
            return true;
          }
          return !group.hideOnRoutes.some((route) =>
            currentRoute.startsWith(route),
          );
        })
        .filter((group) => {
          return group.jobs.some(
            (job) => job.progress > 0 && job.progress < 100,
          );
        });
    },
    [jobGroups],
  );

  const hasActiveJobs = Array.from(jobGroups.values()).some((group) =>
    group.jobs.some((job) => job.progress > 0 && job.progress < 100),
  );

  return (
    <BackgroundJobsContext.Provider
      value={{
        jobGroups,
        registerJobGroup,
        unregisterJobGroup,
        updateJobs,
        getVisibleJobGroups,
        hasActiveJobs,
      }}
    >
      {children}
    </BackgroundJobsContext.Provider>
  );
};
