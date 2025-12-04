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

const Videos = () => {
  const { data: videos, isSuccess } = useGetVideosQuery();

  if (isSuccess && videos.length > 0) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">
          <h1 className="text-3xl font-bold mb-6">Videos</h1>
          <Table>
            <TableCaption>A list of loaded videos.</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[25%]">File name</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Frames</TableHead>
                <TableHead>Codec</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {videos.map((video) => (
                <TableRow key={video.filename}>
                  <TableCell className="font-medium">
                    {video.filename}
                  </TableCell>
                  <TableCell>
                    {video.width}x{video.height}
                  </TableCell>
                  <TableCell>{video.frame_count}</TableCell>
                  <TableCell>{video.codec}</TableCell>
                  <TableCell>{video.duration}</TableCell>
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
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading videos</div>
    </div>
  );
};

export default Videos;
