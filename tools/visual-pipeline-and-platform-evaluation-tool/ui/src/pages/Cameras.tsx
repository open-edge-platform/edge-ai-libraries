import { useGetCamerasQuery, useGetVideosQuery } from "@/api/api.generated.ts";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { formatElapsedTimeSeconds } from "@/lib/timeUtils.ts";

export const Cameras = () => {
    const { data: cameras, isSuccess } = useGetCamerasQuery();

    if (isSuccess && cameras.length > 0) {
    return (
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Cameras</h1>
          <p className="text-muted-foreground mt-2">
            Ready-to-use camera feeds available in the platform
          </p>
        </div>
        <Table>
          <TableCaption>A list of loaded cameras.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[25%]">Camera name</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Number of frames</TableHead>
              <TableHead>Codec</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          {/* <TableBody>
            {cameras.map((camera) => (
              <TableRow key={camera.id}>
                <TableCell className="font-medium">{camera.name}</TableCell>
                <TableCell>
                  {camera.width}x{camera.height}
                </TableCell>
                <TableCell>{camera.frame_count}</TableCell>
                <TableCell>{camera.codec}</TableCell>
                <TableCell>
                  {formatElapsedTimeSeconds(camera.duration)}
                </TableCell>
                <TableCell>
                  <video
                    src={`/assets/videos/input/${camera.filename}`}
                    controls
                    className="w-48 h-auto"
                  >
                    Your browser does not support the video tag.
                  </video>
                </TableCell>
              </TableRow>
            ))}
          </TableBody> */}
        </Table>
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading cameras...</div>
    </div>
  );

}