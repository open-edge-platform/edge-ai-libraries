import { useGetVideosQuery } from "@/api/api.generated.ts";
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

export const Videos = () => {
  const { data: videos, isSuccess } = useGetVideosQuery();

  if (isSuccess && videos.length > 0) {
    return (
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Videos</h1>
          <p className="text-muted-foreground mt-2">
            Ready-to-use video clips available in the platform
          </p>
        </div>
        <Table>
          <TableCaption>A list of loaded videos.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[25%]">File name</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Number of frames</TableHead>
              <TableHead>Codec</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {videos.map((video) => (
              <TableRow key={video.filename}>
                <TableCell className="font-medium">{video.filename}</TableCell>
                <TableCell>
                  {video.width}x{video.height}
                </TableCell>
                <TableCell>{video.frame_count}</TableCell>
                <TableCell>{video.codec}</TableCell>
                <TableCell>
                  {formatElapsedTimeSeconds(video.duration)}
                </TableCell>
                <TableCell>
                  <video
                    src={`/assets/videos/input/${video.filename}`}
                    controls
                    className="w-48 h-auto"
                  >
                    Your browser does not support the video tag.
                  </video>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading videos</div>
    </div>
  );
};
