import { useMemo, useState } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useGetBenchmarkSuitesQuery,
  useGetInstancesQuery,
  useStartExperimentMutation,
} from "@/api/portalApi";
import { formatDeviceName } from "@/lib/utils";
import { toast } from "@/lib/toast";

export const NewExperimentDialog = () => {
  const [open, setOpen] = useState(false);
  const [suiteSlug, setSuiteSlug] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const { data: suites, isLoading: suitesLoading } = useGetBenchmarkSuitesQuery(
    undefined,
    { skip: !open },
  );
  const { data: instances } = useGetInstancesQuery();
  const [startExperiment, { isLoading: isStarting }] =
    useStartExperimentMutation();

  const suite = suites?.find((entry) => entry.slug === suiteSlug);
  const candidates = useMemo(
    () => (instances ?? []).filter((instance) => instance.enabled),
    [instances],
  );

  const supports = (instanceId: number) =>
    !suite || suite.instance_ids.includes(instanceId);
  const runnable = (instanceId: number) => {
    const instance = candidates.find((entry) => entry.id === instanceId);
    return Boolean(instance?.reachable) && supports(instanceId);
  };
  const chosen = selectedIds.filter(runnable);

  const reset = () => {
    setSuiteSlug("");
    setSelectedIds([]);
  };

  const handleStart = async () => {
    try {
      await startExperiment({
        suite_slug: suiteSlug,
        instance_ids: chosen,
      }).unwrap();
      toast.success(
        `Started ${suite?.name ?? suiteSlug} on ${chosen.length} machine${
          chosen.length === 1 ? "" : "s"
        }.`,
      );
      reset();
      setOpen(false);
    } catch (error) {
      const detail =
        (error as { data?: { detail?: string } })?.data?.detail ??
        "Could not start the experiment.";
      toast.error(detail);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Play className="h-4 w-4" />
          New experiment
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[34rem]">
        <DialogHeader>
          <DialogTitle>Run a benchmark suite</DialogTitle>
          <DialogDescription>
            The suite is started on every selected machine, and the resulting
            runs stay grouped as one experiment.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-5 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="experiment-suite">Suite</Label>
            <Select
              value={suiteSlug}
              onValueChange={setSuiteSlug}
              disabled={suitesLoading}
            >
              <SelectTrigger id="experiment-suite" className="w-full">
                <SelectValue
                  placeholder={
                    suitesLoading ? "Loading suites…" : "Select a suite"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {(suites ?? []).map((entry) => (
                  <SelectItem key={entry.slug} value={entry.slug}>
                    {entry.name} ({entry.workload_count} workloads)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {suite?.description ? (
              <p className="text-xs text-muted-foreground">
                {suite.description}
              </p>
            ) : null}
          </div>

          <div className="grid gap-2">
            <Label>Machines</Label>
            {candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No machine is enabled for aggregation.
              </p>
            ) : null}
            {candidates.map((instance) => {
              const offline = !instance.reachable;
              const unsupported = !supports(instance.id);
              const disabled = offline || unsupported;

              return (
                <div key={instance.id} className="flex items-start gap-2">
                  <Checkbox
                    id={`experiment-instance-${instance.id}`}
                    className="mt-0.5"
                    disabled={disabled}
                    checked={selectedIds.includes(instance.id) && !disabled}
                    onCheckedChange={(checked) =>
                      setSelectedIds((current) =>
                        checked === true
                          ? [...current, instance.id]
                          : current.filter((id) => id !== instance.id),
                      )
                    }
                  />
                  <Label
                    htmlFor={`experiment-instance-${instance.id}`}
                    className="grid gap-0.5 font-normal"
                  >
                    <span className="font-medium">{instance.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {offline
                        ? "Offline"
                        : unsupported
                          ? "Suite not available on this machine"
                          : formatDeviceName(instance.cpu) || instance.url}
                    </span>
                  </Label>
                </div>
              );
            })}
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleStart}
            disabled={isStarting || !suiteSlug || chosen.length === 0}
          >
            <Play className="h-4 w-4" />
            Start on {chosen.length} machine{chosen.length === 1 ? "" : "s"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
