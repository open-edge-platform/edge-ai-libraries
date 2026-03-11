import {
  type Camera,
  type NetworkCameraDetails,
  type UsbCameraDetails,
  useGetCamerasQuery,
} from "@/api/api.generated.ts";
import { Badge } from "@/components/ui/badge.tsx";
import {
  mockCameras,
  isCameraMockEnabled,
} from "@/features/cameras/mockCameras.ts";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { CameraAuthDialog } from "@/features/cameras/CameraAuthDialog.tsx";

const getUsbDetails = (camera: Camera): UsbCameraDetails | null =>
  camera.device_type === "USB" ? (camera.details as UsbCameraDetails) : null;

const getNetworkDetails = (camera: Camera): NetworkCameraDetails | null =>
  camera.device_type === "NETWORK"
    ? (camera.details as NetworkCameraDetails)
    : null;

const formatCameraResolution = (camera: Camera): string => {
  if (camera.device_type === "NETWORK") {
    const networkDetails = getNetworkDetails(camera);

    return networkDetails?.best_profile?.resolution ?? "-";
  }

  const usbDetails = getUsbDetails(camera);
  const bestCapture = usbDetails?.best_capture;

  if (!bestCapture) {
    return "-";
  }

  return `${bestCapture.width}x${bestCapture.height}`;
};

const formatCameraFramerate = (camera: Camera): string => {
  if (camera.device_type === "NETWORK") {
    const networkDetails = getNetworkDetails(camera);
    const framerate = networkDetails?.best_profile?.framerate;

    return framerate != null ? `${framerate} FPS` : "-";
  }

  const usbDetails = getUsbDetails(camera);
  const fps = usbDetails?.best_capture?.fps;

  return fps != null ? `${fps} FPS` : "-";
};

export const Cameras = () => {
  const {
    data: cameras,
    isSuccess,
    isLoading,
    isError,
    refetch,
  } = useGetCamerasQuery(undefined, { skip: isCameraMockEnabled });

  const resolvedCameras = isCameraMockEnabled ? mockCameras : (cameras ?? []);
  const resolvedIsSuccess = isCameraMockEnabled ? true : isSuccess;
  const resolvedIsLoading = isCameraMockEnabled ? false : isLoading;
  const resolvedIsError = isCameraMockEnabled ? false : isError;
  const refetchCameras = isCameraMockEnabled
    ? () => Promise.resolve()
    : refetch;

  if (resolvedIsSuccess && resolvedCameras.length > 0) {
    return (
      <div className="container pl-16 mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Cameras</h1>
          <p className="text-muted-foreground mt-2">
            Cameras discovered in the platform
          </p>
        </div>
        <Table>
          <TableCaption>A list of loaded cameras.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[24%]">Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Framerate</TableHead>
              <TableHead className="w-[28%]">Authorization</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {resolvedCameras.map((camera) => {
              const isNetworkCamera = camera.device_type === "NETWORK";
              const networkDetails = getNetworkDetails(camera);
              const usbDetails = getUsbDetails(camera);

              return (
                <TableRow key={camera.device_id}>
                  <TableCell className="font-medium">
                    {camera.device_name}
                  </TableCell>
                  <TableCell>
                    <Badge variant={isNetworkCamera ? "secondary" : "outline"}>
                      {camera.device_type}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {isNetworkCamera
                      ? `${networkDetails?.ip ?? "-"}:${networkDetails?.port ?? "-"}`
                      : (usbDetails?.device_path ?? "-")}
                  </TableCell>
                  <TableCell>{formatCameraResolution(camera)}</TableCell>
                  <TableCell>{formatCameraFramerate(camera)}</TableCell>
                  <TableCell>
                    {isNetworkCamera ? (
                      (networkDetails?.profiles?.length ?? 0) > 0 ? (
                        <div className="flex items-center gap-2">
                          <Badge variant="default">Authorized</Badge>
                        </div>
                      ) : (
                        <CameraAuthDialog
                          cameraId={camera.device_id}
                          cameraName={camera.device_name}
                          onSuccess={() => void refetchCameras()}
                        />
                      )
                    ) : (
                      <span className="text-muted-foreground text-sm">
                        Not required
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    );
  }

  if (resolvedIsLoading) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10 pl-16">Loading cameras...</div>
      </div>
    );
  }

  if (resolvedIsError) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10 pl-16 text-destructive">
          Failed to load cameras.
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10 pl-16">
        <h1 className="text-3xl font-bold">Cameras</h1>
        <p className="text-muted-foreground mt-2">No cameras discovered.</p>
      </div>
    </div>
  );
};
