import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Loader2 } from "lucide-react";
import { useLocation } from "react-router";

export const BackgroundJobsWidget = () => {
  const { getVisibleJobGroups } = useBackgroundJobs();
  const location = useLocation();

  const visibleJobGroups = getVisibleJobGroups(location.pathname);

  if (visibleJobGroups.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-64">
      <Card className="shadow-lg p-3">
        <div className="space-y-3">
          <div className="flex items-center gap-2 pb-2 border-b">
            <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
            <span className="text-sm font-semibold">Background Jobs</span>
          </div>

          {visibleJobGroups.map((group) => {
            const groupProgress =
              group.jobs.length > 0
                ? group.jobs.reduce((sum, job) => sum + job.progress, 0) /
                  group.jobs.length
                : 0;

            return (
              <div key={group.id} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{group.name}</span>
                  <span className="font-medium">
                    {Math.round(groupProgress)}%
                  </span>
                </div>
                <Progress value={groupProgress} className="h-1.5" />
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
};
