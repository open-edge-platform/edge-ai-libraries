import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useAddInstanceMutation,
  useDeleteInstanceMutation,
  useGetInstancesQuery,
  useUpdateInstanceMutation,
} from "@/api/portalApi";
import {
  CONTENT_CONTAINER_CLASS,
  cpuGeneration,
  formatDeviceName,
} from "@/lib/utils";
import { toast } from "@/lib/toast";
import { Plus, Trash2 } from "lucide-react";

export const Instances = () => {
  const { data: instances, isLoading } = useGetInstancesQuery(undefined, {
    pollingInterval: 30_000,
  });
  const [addInstance, { isLoading: isAdding }] = useAddInstanceMutation();
  const [updateInstance] = useUpdateInstanceMutation();
  const [deleteInstance] = useDeleteInstanceMutation();

  const [url, setUrl] = useState("");
  const [name, setName] = useState("");

  const handleAdd = async () => {
    if (!url.trim()) return;
    try {
      await addInstance({
        url: url.trim(),
        name: name.trim() || undefined,
      }).unwrap();
      setUrl("");
      setName("");
      toast.success("Instance added.");
    } catch (error) {
      const detail =
        (error as { data?: { detail?: string } })?.data?.detail ??
        "Could not add the instance.";
      toast.error(detail);
    }
  };

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <h1 className="mb-2 text-3xl font-bold">Instances</h1>
      <p className="mb-6 text-muted-foreground">
        ViPPET machines whose results are aggregated by this portal.
      </p>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="text-lg">Add a machine</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="instance-url">ViPPET URL</Label>
              <Input
                id="instance-url"
                className="w-[22rem]"
                placeholder="http://vippet-host:8080"
                value={url}
                onChange={event => setUrl(event.target.value)}
                onKeyDown={event => event.key === "Enter" && handleAdd()}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="instance-name">Display name (optional)</Label>
              <Input
                id="instance-name"
                className="w-[18rem]"
                placeholder="Lab machine 1"
                value={name}
                onChange={event => setName(event.target.value)}
                onKeyDown={event => event.key === "Enter" && handleAdd()}
              />
            </div>
            <Button onClick={handleAdd} disabled={isAdding || !url.trim()}>
              <Plus className="h-4 w-4" />
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      <Table className="border rounded-lg">
        <TableHeader className="bg-muted">
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>URL</TableHead>
            <TableHead>Platform</TableHead>
            <TableHead>Version</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-center">Included</TableHead>
            <TableHead className="w-[3.5rem]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {instances?.map(instance => (
            <TableRow key={instance.id}>
              <TableCell className="font-medium">{instance.name}</TableCell>
              <TableCell>
                <a
                  href={instance.url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-2"
                >
                  {instance.url}
                </a>
              </TableCell>
              <TableCell className="max-w-[20rem]">
                <div className="truncate font-medium">
                  {cpuGeneration(instance.cpu) || "–"}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {formatDeviceName(instance.cpu) || "–"}
                </div>
              </TableCell>
              <TableCell>{instance.version ?? "–"}</TableCell>
              <TableCell>
                {instance.reachable ? (
                  <Badge variant="success">
                    {instance.ready ? "ready" : (instance.status ?? "online")}
                  </Badge>
                ) : (
                  <Badge
                    variant="destructive"
                    title={instance.error ?? undefined}
                  >
                    offline
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-center">
                <Switch
                  checked={instance.enabled}
                  aria-label={`Include ${instance.name} in aggregation`}
                  onCheckedChange={enabled =>
                    updateInstance({
                      instanceId: instance.id,
                      instanceUpdate: { enabled },
                    })
                  }
                />
              </TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${instance.name}`}
                  onClick={() => deleteInstance(instance.id)}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {!isLoading && (instances?.length ?? 0) === 0 ? (
            <TableRow>
              <TableCell
                colSpan={7}
                className="text-center text-muted-foreground"
              >
                No instances registered.
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>
      <div className="h-10" />
    </div>
  );
};
