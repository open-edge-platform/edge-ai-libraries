import {
  api,
  useGetDefaultVideoRecordingsQuery,
  useGetVideosQuery,
  useLazyCheckVideoInputExistsQuery,
  useStartDefaultVideoDownloadMutation,
  useStartDefaultVideoHevcConversionMutation,
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
import { Button } from "@/components/ui/button.tsx";
import { formatElapsedTimeSeconds } from "@/lib/timeUtils.ts";
import { filterOutTransportStreams } from "@/lib/videoUtils.ts";
import { useEffect, useCallback, useState } from "react";
import { useAppDispatch } from "@/store/hooks";
import { toast } from "sonner";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { MultiFileUploader } from "@/features/upload/MultiFileUploader.tsx";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { Download, ExternalLink, Loader2, RefreshCw } from "lucide-react";

const SAMPLE_DOWNLOAD_LABELS = {
  available: "Download",
  queued: "Downloading",
  downloading: "Downloading",
  downloaded: "Downloaded",
  failed: "Retry",
  conflict: "Name conflict",
};

const HEVC_CONVERSION_LABELS = {
  not_converted: "Convert to HEVC",
  queued: "Queued",
  converting: "Converting",
  converted: "Saved as H.265",
  failed: "Retry HEVC conversion",
  conflict: "Name conflict",
};

export const Videos = () => {
  const { data: videos, isSuccess, isLoading } = useGetVideosQuery();
  const [trackedDownloads, setTrackedDownloads] = useState<string[]>([]);
  const [startingDownloads, setStartingDownloads] = useState<string[]>([]);
  const [trackedConversions, setTrackedConversions] = useState<string[]>([]);
  const [startingConversions, setStartingConversions] = useState<string[]>([]);
  const { data: sampleVideos = [] } = useGetDefaultVideoRecordingsQuery(
    undefined,
    {
      pollingInterval:
        trackedDownloads.length > 0 || trackedConversions.length > 0 ? 2000 : 0,
    },
  );
  const dispatch = useAppDispatch();
  const [checkVideoExists] = useLazyCheckVideoInputExistsQuery();
  const [startDefaultVideoDownload] = useStartDefaultVideoDownloadMutation();
  const [startDefaultVideoHevcConversion] =
    useStartDefaultVideoHevcConversionMutation();
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

  const handleDownload = useCallback(
    async (filename: string) => {
      setStartingDownloads((current) =>
        Array.from(new Set([...current, filename])),
      );
      try {
        const result = await startDefaultVideoDownload({
          defaultVideoDownloadRequest: { filename },
        }).unwrap();
        if (result.status === "queued" || result.status === "downloading") {
          setTrackedDownloads((current) =>
            Array.from(new Set([...current, filename])),
          );
          toast.info("Sample video download started.");
        } else if (result.status === "downloaded") {
          dispatch(api.util.invalidateTags(["videos"]));
          toast.info("This sample video is already downloaded.");
        }
      } catch {
        toast.error("Could not start the sample video download.");
      } finally {
        setStartingDownloads((current) =>
          current.filter((name) => name !== filename),
        );
      }
    },
    [dispatch, startDefaultVideoDownload],
  );

  const handleHevcConversion = useCallback(
    async (filename: string) => {
      setStartingConversions((current) =>
        Array.from(new Set([...current, filename])),
      );
      try {
        const result = await startDefaultVideoHevcConversion({
          defaultVideoConversionRequest: { filename },
        }).unwrap();
        if (result.status === "queued" || result.status === "converting") {
          setTrackedConversions((current) =>
            Array.from(new Set([...current, filename])),
          );
          toast.info("HEVC conversion started.");
        } else if (result.status === "converted") {
          dispatch(api.util.invalidateTags(["videos"]));
          toast.success(`Saved ${result.hevc_filename}.`);
        }
      } catch {
        toast.error("Could not convert the sample video to HEVC.");
      } finally {
        setStartingConversions((current) =>
          current.filter((name) => name !== filename),
        );
      }
    },
    [dispatch, startDefaultVideoHevcConversion],
  );

  useEffect(() => {
    if (trackedDownloads.length === 0) return;
    const finished = trackedDownloads.every((filename) => {
      const sample = sampleVideos.find((video) => video.filename === filename);
      return sample?.status === "downloaded" || sample?.status === "failed";
    });
    if (!finished) return;

    const failed = trackedDownloads.filter(
      (filename) =>
        sampleVideos.find((video) => video.filename === filename)?.status ===
        "failed",
    );
    setTrackedDownloads([]);
    dispatch(api.util.invalidateTags(["videos"]));
    if (failed.length > 0) {
      toast.error(`Could not download ${failed.length} sample video(s).`);
    } else {
      toast.success("Sample video download completed.");
    }
  }, [dispatch, sampleVideos, trackedDownloads]);

  useEffect(() => {
    if (trackedConversions.length === 0) return;
    const finished = trackedConversions.every((filename) => {
      const sample = sampleVideos.find((video) => video.filename === filename);
      return ["converted", "failed", "conflict"].includes(
        sample?.conversion_status ?? "",
      );
    });
    if (!finished) return;

    const failed = trackedConversions.filter((filename) => {
      const status = sampleVideos.find(
        (video) => video.filename === filename,
      )?.conversion_status;
      return status === "failed" || status === "conflict";
    });
    const converted = trackedConversions
      .map((filename) =>
        sampleVideos.find((video) => video.filename === filename),
      )
      .filter((video) => video?.conversion_status === "converted");
    setTrackedConversions([]);
    dispatch(api.util.invalidateTags(["videos"]));
    if (failed.length > 0) {
      toast.error(
        `Could not convert ${failed.length} sample video(s) to HEVC.`,
      );
    } else if (converted.length > 0) {
      toast.success(`Saved ${converted[0]?.hevc_filename} as H.265.`);
    }
  }, [dispatch, sampleVideos, trackedConversions]);

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
    <div className={CONTENT_CONTAINER_CLASS}>
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Videos</h1>
        <p className="text-muted-foreground mt-2">
          Ready-to-use video clips available in the platform
        </p>
      </div>

      <MultiFileUploader
        accept="video/*"
        maxSize={2 * 1024 * 1024 * 1024} // 2 GB
        uploadEndpoint={ENDPOINTS.UPLOAD_VIDEO}
        checkFileExists={handleCheckFileExists}
        onUploadProgress={handleUploadProgress}
        onUploadComplete={handleUploadComplete}
        multiple={true}
        maxConcurrentUploads={3}
        className="mb-8"
      />

      <section className="mb-10">
        <div className="mb-4">
          <h2 className="text-xl font-semibold">Sample videos</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Download sample clips individually when you need them.
          </p>
        </div>

        <div className="mb-4 border-l-4 border-primary bg-muted/40 px-4 py-3 text-sm">
          <p className="font-medium">Pexels sample video terms</p>
          <p className="mt-1 text-muted-foreground">
            Some clips are from Pexels. Attribution is not required under its
            current license, but bulk or systematic copying is restricted, so
            download Pexels clips individually. Review the{" "}
            <a
              className="inline-flex items-center gap-1 text-foreground underline underline-offset-4"
              href="https://www.pexels.com/license/"
              target="_blank"
              rel="noreferrer"
            >
              Pexels License <ExternalLink className="size-3" />
            </a>{" "}
            and{" "}
            <a
              className="inline-flex items-center gap-1 text-foreground underline underline-offset-4"
              href="https://www.pexels.com/terms-of-service/"
              target="_blank"
              rel="noreferrer"
            >
              Terms of Service <ExternalLink className="size-3" />
            </a>
            .
          </p>
        </div>
        <p className="mb-3 text-sm text-muted-foreground">
          HEVC conversion uses the DLSPS VA-API encoder and requires an
          available Intel GPU.
        </p>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File name</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sampleVideos.map((video) => {
              const isPending =
                video.status === "queued" || video.status === "downloading";
              const isStartingThisDownload = startingDownloads.includes(
                video.filename,
              );
              const isDownloaded = video.status === "downloaded";
              const hasNameConflict = video.status === "conflict";
              const isConverting =
                video.conversion_status === "queued" ||
                video.conversion_status === "converting";
              const isStartingThisConversion = startingConversions.includes(
                video.filename,
              );
              const hasConversionConflict =
                video.conversion_status === "conflict";
              const isConverted = video.conversion_status === "converted";
              return (
                <TableRow key={video.filename}>
                  <TableCell className="font-medium">
                    {video.filename}
                  </TableCell>
                  <TableCell>{video.source}</TableCell>
                  <TableCell className="capitalize">
                    {video.status.replaceAll("_", " ")}
                  </TableCell>
                  <TableCell className="text-right">
                    {isDownloaded ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={
                          isConverting ||
                          isStartingThisConversion ||
                          isConverted ||
                          hasConversionConflict
                        }
                        onClick={() => handleHevcConversion(video.filename)}
                      >
                        {isConverting || isStartingThisConversion ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : isConverted || hasConversionConflict ? null : (
                          <RefreshCw className="size-4" />
                        )}
                        {HEVC_CONVERSION_LABELS[video.conversion_status]}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={
                          isPending || isStartingThisDownload || hasNameConflict
                        }
                        onClick={() => handleDownload(video.filename)}
                      >
                        {isPending || isStartingThisDownload ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : hasNameConflict ? null : (
                          <Download className="size-4" />
                        )}
                        {SAMPLE_DOWNLOAD_LABELS[video.status]}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </section>

      {filteredVideos.length > 0 ? (
        <Table className="mb-10">
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
                <TableCell className="font-medium max-w-0">
                  <div className="truncate" title={video.filename}>
                    {video.filename}
                  </div>
                </TableCell>
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
                    src={`/assets/videos/input/${video.path}`}
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
