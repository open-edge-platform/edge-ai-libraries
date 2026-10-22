import { useMemo, useState } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
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
  useGetInstancesQuery,
  useGetPipelineCatalogQuery,
  useStartTestExperimentMutation,
  type TestKind,
} from "@/api/portalApi";
import { formatDeviceName } from "@/lib/utils";
import { toast } from "@/lib/toast";

export const NewTestDialog = ({ kind }: { kind: TestKind }) => {
  const [open, setOpen] = useState(false);
  const [pipelineId, setPipelineId] = useState("");
  const [variantId, setVariantId] = useState("");
  const [streams, setStreams] = useState("1");
  const [maxRuntime, setMaxRuntime] = useState("5");
  const [fpsFloor, setFpsFloor] = useState("30");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const { data: pipelines, isLoading: pipelinesLoading } =
    useGetPipelineCatalogQuery(undefined, { skip: !open });
  const { data: instances } = useGetInstancesQuery();
  const [startTest, { isLoading: isStarting }] =
    useStartTestExperimentMutation();

  const pipeline = pipelines?.find((entry) => entry.id === pipelineId);
  const candidates = useMemo(
    () => (instances ?? []).filter((instance) => instance.enabled),
    [instances],
  );

  const supports = (instanceId: number) =>
    !pipeline || pipeline.instance_ids.includes(instanceId);
  const runnable = (instanceId: number) => {
    const instance = candidates.find((entry) => entry.id === instanceId);
    return Boolean(instance?.reachable) && supports(instanceId);
  };
  const chosen = selectedIds.filter(runnable);

  const reset = () => {
    setPipelineId("");
    setVariantId("");
    setSelectedIds([]);
  };

  const handleStart = async () => {
    try {
      await startTest({
        kind,
        pipeline_id: pipelineId,
        variant_id: variantId,
        instance_ids: chosen,
        streams: Number(streams) || 1,
        max_runtime: kind === "density" ? Number(maxRuntime) || 0 : 0,
        fps_floor: Number(fpsFloor) || 30,
      }).unwrap();
      toast.success(
        `Started on ${chosen.length} machine${chosen.length === 1 ? "" : "s"}.`,
      );
      reset();
      setOpen(false);
    } catch (error) {
      const detail =
        (error as { data?: { detail?: string } })?.data?.detail ??
        "Could not start the test.";
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
          <DialogTitle>
            Run a {kind === "density" ? "density" : "performance"} test
          </DialogTitle>
          <DialogDescription>
            The same workload is started on every selected machine, and the
            resulting jobs stay grouped as one experiment.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-5 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="test-pipeline">Pipeline</Label>
            <Select
              value={pipelineId}
              onValueChange={(value) => {
                setPipelineId(value);
                setVariantId("");
              }}
              disabled={pipelinesLoading}
            >
              <SelectTrigger id="test-pipeline" className="w-full">
                <SelectValue
                  placeholder={
                    pipelinesLoading
                      ? "Loading pipelines…"
                      : "Select a pipeline"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {(pipelines ?? []).map((entry) => (
                  <SelectItem key={entry.id} value={entry.id}>
                    {entry.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-wrap items-end gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="test-variant">Variant</Label>
              <Select
                value={variantId}
                onValueChange={setVariantId}
                disabled={!pipeline}
              >
                <SelectTrigger id="test-variant" className="w-[12rem]">
                  <SelectValue placeholder="Select a variant" />
                </SelectTrigger>
                <SelectContent>
                  {(pipeline?.variants ?? []).map((variant) => (
                    <SelectItem key={variant.id} value={variant.id}>
                      {variant.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {kind === "performance" ? (
              <div className="grid gap-1.5">
                <Label htmlFor="test-streams">Streams</Label>
                <Input
                  id="test-streams"
                  type="number"
                  min={1}
                  className="w-[7rem]"
                  value={streams}
                  onChange={(event) => setStreams(event.target.value)}
                />
              </div>
            ) : (
              <>
                <div className="grid gap-1.5">
                  <Label htmlFor="test-fps-floor">FPS floor</Label>
                  <Input
                    id="test-fps-floor"
                    type="number"
                    min={1}
                    className="w-[9rem]"
                    value={fpsFloor}
                    onChange={(event) => setFpsFloor(event.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="test-runtime">Iteration duration (s)</Label>
                  <Input
                    id="test-runtime"
                    type="number"
                    min={0}
                    className="w-[11rem]"
                    value={maxRuntime}
                    onChange={(event) => setMaxRuntime(event.target.value)}
                  />
                </div>
              </>
            )}
          </div>
          {kind === "density" ? (
            <p className="-mt-3 text-xs text-muted-foreground">
              How long each stream-count iteration runs. 0 runs every iteration
              to the end of its video.
            </p>
          ) : null}

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
                    id={`test-instance-${instance.id}`}
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
                    htmlFor={`test-instance-${instance.id}`}
                    className="grid gap-0.5 font-normal"
                  >
                    <span className="font-medium">{instance.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {offline
                        ? "Offline"
                        : unsupported
                          ? "Pipeline not available on this machine"
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
            disabled={
              isStarting || !pipelineId || !variantId || chosen.length === 0
            }
          >
            <Play className="h-4 w-4" />
            Start on {chosen.length} machine{chosen.length === 1 ? "" : "s"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
