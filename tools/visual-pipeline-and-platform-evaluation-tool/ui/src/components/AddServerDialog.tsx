import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog.tsx";
import { Button } from "@/components/ui/button.tsx";
import { toast } from "sonner";
import { ServerIcon, Loader2 } from "lucide-react";
import { API_BASE_URL, ADMIN_API_KEY, SERVERS_BASE_URL } from "@/api/apiSlice.ts";

type SystemInfo = {
  uuid: string;
  ip_address: string;
  cpu_sku: string;
  ram_size: number;
  kernel_version: string;
};

export const AddServerDialog = () => {
  const [open, setOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [isRegistered, setIsRegistered] = useState(false);

  const checkIfRegistered = async (uuid: string) => {
    try {
      const response = await fetch(`${SERVERS_BASE_URL}/servers`);
      if (!response.ok) {
        return false;
      }
      const data = await response.json();
      const servers = data.servers || [];
      return servers.some((server: SystemInfo) => server.uuid === uuid);
    } catch (error) {
      return false;
    }
  };

  const fetchSystemInfo = async () => {
    setIsFetching(true);
    try {
      const response = await fetch(`${API_BASE_URL}/sysinfo`);

      if (!response.ok) {
        throw new Error("Failed to fetch system information");
      }

      const data = await response.json();
      setSystemInfo(data);

      // Check if this machine is already registered
      const registered = await checkIfRegistered(data.uuid);
      setIsRegistered(registered);
    } catch (error) {
      toast.error("Failed to fetch system information", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
      setOpen(false);
    } finally {
      setIsFetching(false);
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (newOpen) {
      fetchSystemInfo();
    } else {
      setSystemInfo(null);
      setIsRegistered(false);
    }
  };

  const handleRegister = async () => {
    if (!systemInfo) return;

    setIsLoading(true);
    try {
      const response = await fetch(`${SERVERS_BASE_URL}/servers`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(ADMIN_API_KEY && { "X-Admin-Key": ADMIN_API_KEY }),
        },
        body: JSON.stringify(systemInfo),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || "Failed to add server");
      }

      toast.success("Server registered", {
        description: "This machine has been registered successfully",
      });

      setOpen(false);
    } catch (error) {
      toast.error("Failed to register server", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemove = async () => {
    if (!systemInfo) return;

    setIsLoading(true);
    try {
      const response = await fetch(
        `${SERVERS_BASE_URL}/servers/${encodeURIComponent(systemInfo.uuid)}`,
        {
          method: "DELETE",
          headers: {
            ...(ADMIN_API_KEY && { "X-Admin-Key": ADMIN_API_KEY }),
          },
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || "Failed to remove server");
      }

      toast.success("Server removed", {
        description: "This machine has been unregistered successfully",
      });

      setOpen(false);
    } catch (error) {
      toast.error("Failed to remove server", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = () => {
    if (isRegistered) {
      handleRemove();
    } else {
      handleRegister();
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Register server">
          <ServerIcon className="w-5 h-5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {isRegistered ? "Remove Server" : "Register Server"}
          </DialogTitle>
          <DialogDescription>
            {isRegistered
              ? "This machine is currently registered. You can remove it from the server registry."
              : "Confirm the automatically detected system information before registering this machine"}
          </DialogDescription>
        </DialogHeader>

        {isFetching ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            <span className="ml-3 text-muted-foreground">
              Detecting system information...
            </span>
          </div>
        ) : systemInfo ? (
          <div className="space-y-3 py-4">
            {isRegistered && (
              <div className="bg-muted/50 border border-muted-foreground/20 rounded-md p-3 mb-3">
                <p className="text-sm text-muted-foreground">
                  ✓ This machine is currently registered
                </p>
              </div>
            )}
            <div className="grid grid-cols-3 gap-2">
              <div className="font-medium text-sm text-muted-foreground">
                UUID:
              </div>
              <div className="col-span-2 text-sm font-mono break-all">
                {systemInfo.uuid}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="font-medium text-sm text-muted-foreground">
                IP Address:
              </div>
              <div className="col-span-2 text-sm">{systemInfo.ip_address}</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="font-medium text-sm text-muted-foreground">
                CPU:
              </div>
              <div className="col-span-2 text-sm break-words">
                {systemInfo.cpu_sku}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="font-medium text-sm text-muted-foreground">
                RAM:
              </div>
              <div className="col-span-2 text-sm">{systemInfo.ram_size} GB</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="font-medium text-sm text-muted-foreground">
                Kernel:
              </div>
              <div className="col-span-2 text-sm font-mono">
                {systemInfo.kernel_version}
              </div>
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isLoading || isFetching}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isLoading || isFetching || !systemInfo}
            variant={isRegistered ? "destructive" : "default"}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                {isRegistered ? "Removing..." : "Registering..."}
              </>
            ) : isRegistered ? (
              "Remove Server"
            ) : (
              "Register Server"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
