import {
  api,
  useGetVideosQuery,
  useLazyCheckVideoInputExistsQuery,
} from "@/api/api.generated.ts";
import { ENDPOINTS } from "@/api/apiEndpoints";
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
import { filterOutTransportStreams } from "@/lib/videoUtils.ts";
import { useEffect, useCallback } from "react";
import { useAppDispatch } from "@/store/hooks";
import { toast } from "sonner";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { MultiFileUploader } from "@/components/shared/MultiFileUploader.tsx";

export const Videos = () => {
  const { data: videos, isSuccess, isLoading } = useGetVideosQuery();
  const dispatch = useAppDispatch();
  const [checkVideoExists] = useLazyCheckVideoInputExistsQuery();
  const { registerJobGroup, unregisterJobGroup, updateJobs } =
    useBackgroundJobs();

  // Register this component as a job group
  useEffect(() => {
    registerJobGroup("videos", "Video Uploads", ["/videos"]);
    return () => {
      unregisterJobGroup("videos");
    };
  }, [registerJobGroup, unregisterJobGroup]);

  const handleCheckFileExists = useCallback(
    async (filename: string): Promise<{ exists: boolean }> => {
      try {
        const result = await checkVideoExists({ filename }).unwrap();
        return { exists: result.exists };
      } catch (error) {
        console.error(`Error checking file ${filename}:`, error);
        return { exists: false };
      }
    },
    [checkVideoExists],
  );

  const handleUploadProgress = useCallback(
    (jobs: Array<{ id: string; name: string; progress: number }>) => {
      updateJobs("videos", jobs);
    },
    [updateJobs],
  );

  const handleUploadComplete = useCallback(
    (succeeded: number, failed: number) => {
      if (failed === 0 && succeeded > 0) {
        dispatch(api.util.invalidateTags(["videos"]));
        toast.success("Upload completed.");
      } else if (succeeded > 0 && failed > 0) {
        toast.warning(
          `${succeeded} file(s) uploaded successfully. ${failed} failed.`,
        );
        dispatch(api.util.invalidateTags(["videos"]));
      } else if (failed > 0) {
        toast.error(`Upload failed for ${failed} file(s).`);
      }
    },
    [dispatch],
  );

  const filteredVideos =
    isSuccess && videos ? filterOutTransportStreams(videos) : [];

  if (isLoading) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">Loading videos...</div>
      </div>
    );
  }

  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Videos</h1>
        <p className="text-muted-foreground mt-2">
          Ready-to-use video clips available in the platform
        </p>
      </div>

      <MultiFileUploader
        accept="video/*"
        uploadEndpoint={ENDPOINTS.UPLOAD_VIDEO}
        checkFileExists={handleCheckFileExists}
        onUploadProgress={handleUploadProgress}
        onUploadComplete={handleUploadComplete}
        multiple={true}
        maxConcurrentUploads={3}
        className="mb-8"
      />

      {filteredVideos.length > 0 ? (
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
            {filteredVideos.map((video) => (
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
      ) : (
        <div className="text-center py-10 text-muted-foreground">
          No videos uploaded yet. Upload your first video above.
        </div>
      )}
    </div>
  );
};
