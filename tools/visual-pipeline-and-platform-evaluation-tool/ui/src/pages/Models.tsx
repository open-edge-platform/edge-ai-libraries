import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { useEffect, useState, useRef } from "react";
import { Button } from "@/components/ui/button";

export const Models = () => {
  const models = useAppSelector(selectModels);
  const { registerJobGroup, unregisterJobGroup, updateJobs } =
    useBackgroundJobs();
  const [isJobRunning, setIsJobRunning] = useState(false);
  const intervalRef = useRef<number | null>(null);

  // Register job group
  useEffect(() => {
    registerJobGroup("models", "Model Processing", ["/models"]);
    return () => {
      unregisterJobGroup("models");
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [registerJobGroup, unregisterJobGroup]);

  const startTestJob = () => {
    setIsJobRunning(true);
    const startTime = Date.now();
    const duration = 60000; // 1 minute in ms

    intervalRef.current = window.setInterval(() => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min((elapsed / duration) * 100, 100);

      updateJobs("models", [
        {
          id: "test-model-job",
          name: "Test Model Processing",
          progress,
        },
      ]);

      if (progress >= 100) {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        setIsJobRunning(false);
        // Clear the job after completion
        setTimeout(() => {
          updateJobs("models", []);
        }, 1000);
      }
    }, 100); // Update every 100ms for smooth progress
  };

  if (models.length > 0) {
    return (
      <div className="container pl-16 mx-auto py-10">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Models</h1>
            <p className="text-muted-foreground mt-2">
              Ready-to-use models available in the platform
            </p>
          </div>
          <Button onClick={startTestJob} disabled={isJobRunning}>
            {isJobRunning ? "Job Running..." : "Start Test Job (1 min)"}
          </Button>
        </div>
        <Table>
          <TableCaption>A list of loaded models.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[33%]">Name</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Precision</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model) => (
              <TableRow key={model.name}>
                <TableCell className="font-medium">
                  {model.display_name}
                </TableCell>
                <TableCell>{model.category}</TableCell>
                <TableCell>{model.precision}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">
        <div className="flex items-center justify-between mb-6">
          <p>Loading models</p>
          <Button onClick={startTestJob} disabled={isJobRunning}>
            {isJobRunning ? "Job Running..." : "Start Test Job (1 min)"}
          </Button>
        </div>
      </div>
    </div>
  );
};
