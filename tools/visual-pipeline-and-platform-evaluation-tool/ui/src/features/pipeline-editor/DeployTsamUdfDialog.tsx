import { useRef, useState } from "react";
import { PackageCheck, Upload } from "lucide-react";
import { toast } from "sonner";
import { API_BASE_URL } from "@/api/apiSlice";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type PackageSource = "upload" | "model-download";

type DeployTsamUdfDialogProps = {
  device: string | undefined;
};

export const DeployTsamUdfDialog = ({ device }: DeployTsamUdfDialogProps) => {
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<PackageSource>("model-download");
  const [file, setFile] = useState<File | null>(null);
  const [isDeploying, setIsDeploying] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canDeploy =
    !isDeploying &&
    !!device &&
    (source === "model-download" || file?.name.endsWith(".tar"));

  const deploy = async () => {
    if (!canDeploy) return;

    const formData = new FormData();
    formData.append("source", source);
    if (source === "upload" && file) {
      formData.append("file", file);
    }
    formData.append("device", device);

    setIsDeploying(true);
    try {
      const response = await fetch(`${API_BASE_URL}/timeseries/udfs/deploy`, {
        method: "POST",
        body: formData,
      });
      const responseText = await response.text();
      let payload: {
        udf_name?: string;
        message?: string;
        detail?: string;
      } = {};
      if (responseText) {
        try {
          payload = JSON.parse(responseText) as typeof payload;
        } catch {
          payload.detail = responseText;
        }
      }
      if (!response.ok) {
        throw new Error(
          payload.detail ?? `UDF deployment failed (HTTP ${response.status})`,
        );
      }
      toast.success(payload.message ?? `Deployed ${payload.udf_name}`);
      setOpen(false);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "UDF deployment failed",
      );
    } finally {
      setIsDeploying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          className="w-[10rem] px-3 py-2 h-auto gap-2 font-medium text-[1.025rem]"
        >
          <PackageCheck className="w-5 h-5" />
          Deploy UDF
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Deploy Time Series UDF</DialogTitle>
          <DialogDescription>
            Deploy a validated UDF package to Time Series Analytics.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="udf-source" className="text-sm font-medium">
              Package source
            </label>
            <Select
              value={source}
              onValueChange={(value) => setSource(value as PackageSource)}
            >
              <SelectTrigger id="udf-source" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="model-download">Model download</SelectItem>
                <SelectItem value="upload">Local tar package</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {source === "model-download" ? (
            <p className="text-sm text-muted-foreground">
              Downloads the Wind Turbine Anomaly Detection package.
            </p>
          ) : (
            <div className="space-y-2">
              <label htmlFor="udf-package-file" className="text-sm font-medium">
                UDF tar package
              </label>
              <Input
                ref={fileInputRef}
                id="udf-package-file"
                type="file"
                accept=".tar,application/x-tar"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </div>
          )}
          <div className="space-y-2">
            <span className="text-sm font-medium">Deployment device</span>
            <div className="flex h-9 items-center border bg-muted/30 px-3 text-sm font-medium uppercase">
              {device ?? "Unavailable"}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={isDeploying}
          >
            Cancel
          </Button>
          <Button onClick={deploy} disabled={!canDeploy}>
            <Upload />
            {isDeploying ? "Deploying" : "Deploy"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
