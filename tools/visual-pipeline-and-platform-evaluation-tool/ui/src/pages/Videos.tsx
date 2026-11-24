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
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { Button } from "@/components/ui/button.tsx";
import { Badge } from "@/components/ui/badge.tsx";
import { formatElapsedTimeSeconds } from "@/lib/timeUtils.ts";
import { filterOutTransportStreams } from "@/lib/videoUtils.ts";
import { useEffect, useCallback, useRef, useState } from "react";
import { useAppDispatch } from "@/store/hooks";
import { toast } from "sonner";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { MultiFileUploader } from "@/features/upload/MultiFileUploader.tsx";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { Download, ExternalLink, Loader2 } from "lucide-react";

const SAMPLE_DOWNLOAD_LABELS = {
  available: "Download",
  failed: "Retry",
};
const SAMPLE_POLL_INTERVAL_MS = 2000;
const SAMPLE_POLL_MAX_ATTEMPTS = 900;

export const Videos = () => {
  const { data: videos, isSuccess, isLoading } = useGetVideosQuery();
  const [isBulkProcessing, setIsBulkProcessing] = useState(false);
  const [bulkCurrentFilename, setBulkCurrentFilename] = useState<string | null>(
    null,
  );
  const [trackedDownloads, setTrackedDownloads] = useState<string[]>([]);
  const [startingDownloads, setStartingDownloads] = useState<string[]>([]);
  const [trackedConversions, setTrackedConversions] = useState<string[]>([]);
  const { data: sampleVideos = [], refetch: refetchSampleVideos } =
    useGetDefaultVideoRecordingsQuery(undefined, {
      pollingInterval:
        trackedDownloads.length > 0 ||
        trackedConversions.length > 0 ||
        isBulkProcessing
          ? 2000
          : 0,
    });
  const dispatch = useAppDispatch();
  const [checkVideoExists] = useLazyCheckVideoInputExistsQuery();
  const [startDefaultVideoDownload] = useStartDefaultVideoDownloadMutation();
  const [startDefaultVideoHevcConversion] =
    useStartDefaultVideoHevcConversionMutation();
  const { registerJobGroup, unregisterJobGroup, updateJobs } =
    useBackgroundJobs();
  const isUnmountedRef = useRef(false);

  useEffect(() => {
    isUnmountedRef.current = false;
    return () => {
      isUnmountedRef.current = true;
    };
  }, []);

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
          setTrackedDownloads((current) =>
            Array.from(new Set([...current, filename])),
          );
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

  const handlePostDownloadProcessing = useCallback(
    async (filename: string) => {
      try {
        const result = await startDefaultVideoHevcConversion({
          defaultVideoConversionRequest: { filename },
        }).unwrap();
        if (result.status === "queued" || result.status === "converting") {
          setTrackedConversions((current) =>
            Array.from(new Set([...current, filename])),
          );
        } else if (result.status === "converted") {
          dispatch(api.util.invalidateTags(["videos"]));
        }
      } catch {
        toast.error("Could not prepare the sample video.");
        dispatch(api.util.invalidateTags(["videos"]));
      }
    },
    [dispatch, startDefaultVideoHevcConversion],
  );

  const bulkCandidates = sampleVideos.filter(
    (video) => video.status !== "conflict" && video.status !== "downloaded",
  );

  const handleDownloadAll = useCallback(async () => {
    if (bulkCandidates.length === 0 || isBulkProcessing) return;
    setIsBulkProcessing(true);
    let completed = 0;
    let failed = 0;

    const waitForVideo = async (
      filename: string,
      isFinished: (video: (typeof sampleVideos)[number]) => boolean,
    ) => {
      for (let attempt = 0; attempt < SAMPLE_POLL_MAX_ATTEMPTS; attempt += 1) {
        await new Promise((resolve) =>
          window.setTimeout(resolve, SAMPLE_POLL_INTERVAL_MS),
        );
        if (isUnmountedRef.current) throw new Error("Page closed");
        const recordings = await refetchSampleVideos().unwrap();
        const video = recordings.find((item) => item.filename === filename);
        if (!video) throw new Error("Sample video is no longer listed");
        if (isFinished(video)) return video;
      }
      throw new Error("Timed out waiting for the sample video");
    };

    try {
      for (const candidate of bulkCandidates) {
        if (isUnmountedRef.current) return;
        setBulkCurrentFilename(candidate.filename);
        try {
          let video = candidate;
          if (video.status !== "downloaded") {
            await startDefaultVideoDownload({
              defaultVideoDownloadRequest: { filename: video.filename },
            }).unwrap();
            // "available" after the start means the backend lost the job, e.g. after a restart.
            video = await waitForVideo(candidate.filename, (current) =>
              ["downloaded", "failed", "conflict", "available"].includes(
                current.status,
              ),
            );
            if (video.status !== "downloaded") {
              throw new Error("Video download failed");
            }
          }

          if (video.conversion_status !== "converted") {
            await startDefaultVideoHevcConversion({
              defaultVideoConversionRequest: { filename: video.filename },
            }).unwrap();
            video = await waitForVideo(candidate.filename, (current) =>
              ["converted", "failed", "conflict", "not_converted"].includes(
                current.conversion_status,
              ),
            );
            if (video.conversion_status !== "converted") {
              throw new Error("HEVC conversion failed");
            }
          }
          completed += 1;
        } catch {
          if (isUnmountedRef.current) return;
          failed += 1;
        }
      }

      dispatch(api.util.invalidateTags(["videos"]));
      if (failed > 0) {
        toast.warning(`${completed} video(s) ready; ${failed} failed.`);
      } else {
        toast.success(`${completed} video(s) ready.`);
      }
    } finally {
      setIsBulkProcessing(false);
      setBulkCurrentFilename(null);
    }
  }, [
    bulkCandidates,
    dispatch,
    isBulkProcessing,
    refetchSampleVideos,
    startDefaultVideoDownload,
    startDefaultVideoHevcConversion,
  ]);

  // Resume tracking jobs that kept running on the backend while the page was closed.
  useEffect(() => {
    if (isBulkProcessing) return;
    const downloading = sampleVideos
      .filter(
        (video) =>
          (video.status === "queued" || video.status === "downloading") &&
          !trackedDownloads.includes(video.filename),
      )
      .map((video) => video.filename);
    const converting = sampleVideos
      .filter(
        (video) =>
          (video.conversion_status === "queued" ||
            video.conversion_status === "converting") &&
          !trackedConversions.includes(video.filename),
      )
      .map((video) => video.filename);
    if (downloading.length > 0) {
      setTrackedDownloads((current) => [
        ...new Set([...current, ...downloading]),
      ]);
    }
    if (converting.length > 0) {
      setTrackedConversions((current) => [
        ...new Set([...current, ...converting]),
      ]);
    }
  }, [isBulkProcessing, sampleVideos, trackedConversions, trackedDownloads]);

  useEffect(() => {
    if (trackedDownloads.length === 0) return;
    const finished = trackedDownloads.every((filename) => {
      const sample = sampleVideos.find((video) => video.filename === filename);
      return ["downloaded", "failed", "conflict"].includes(
        sample?.status ?? "",
      );
    });
    if (!finished) return;

    const failed = trackedDownloads.filter((filename) =>
      ["failed", "conflict"].includes(
        sampleVideos.find((video) => video.filename === filename)?.status ?? "",
      ),
    );
    const downloaded = trackedDownloads.filter(
      (filename) =>
        sampleVideos.find((video) => video.filename === filename)?.status ===
        "downloaded",
    );
    setTrackedDownloads([]);
    dispatch(api.util.invalidateTags(["videos"]));
    downloaded.forEach(
      (filename) => void handlePostDownloadProcessing(filename),
    );
    if (failed.length > 0) {
      toast.error(`Could not download ${failed.length} sample video(s).`);
    } else {
      toast.success("Sample video download completed.");
    }
  }, [dispatch, handlePostDownloadProcessing, sampleVideos, trackedDownloads]);

  useEffect(() => {
    if (trackedConversions.length === 0) return;
    const finished = trackedConversions.every((filename) => {
      const sample = sampleVideos.find((video) => video.filename === filename);
      return ["converted", "failed", "conflict"].includes(
        sample?.conversion_status ?? "",
      );
    });
    if (!finished) return;

    setTrackedConversions([]);
    dispatch(api.util.invalidateTags(["videos"]));
  }, [dispatch, sampleVideos, trackedConversions]);

  const filteredVideos =
    isSuccess && videos ? filterOutTransportStreams(videos) : [];
  const sampleFilenames = new Set(sampleVideos.map((video) => video.filename));
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

      <div className="sticky top-0 z-10 mb-3 flex items-center justify-end gap-3 border-b bg-background py-3">
        <Button
          size="sm"
          disabled={bulkCandidates.length === 0 || isBulkProcessing}
          onClick={handleDownloadAll}
        >
          {isBulkProcessing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Download className="size-4" />
          )}
          {isBulkProcessing
            ? `Processing ${bulkCurrentFilename ?? "videos"}...`
            : `Download all videos (${bulkCandidates.length})`}
        </Button>
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
          <h2 className="text-xl font-semibold">Videos</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Download sample clips or open available videos.
          </p>
        </div>

        <div className="mb-4 border-l-4 border-primary bg-muted/40 px-4 py-3 text-sm">
          <p className="font-medium">Pexels sample video terms</p>
          <p className="mt-1 text-muted-foreground">
            Some clips are from Pexels. Attribution is not required under its
            current license. Review the{" "}
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
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File name</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Codec</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sampleVideos.map((video) => {
              const availableVideo = filteredVideos.find(
                (item) => item.filename === video.filename,
              );
              const isPending =
                video.status === "queued" || video.status === "downloading";
              const isStartingThisDownload = startingDownloads.includes(
                video.filename,
              );
              const isDownloaded = video.status === "downloaded";
              const hasNameConflict = video.status === "conflict";
              const isBulkCurrent =
                isBulkProcessing && bulkCurrentFilename === video.filename;
              const isDownloading =
                isPending ||
                isStartingThisDownload ||
                (isBulkCurrent && !isDownloaded);
              const isConverting =
                isDownloaded &&
                (video.conversion_status === "queued" ||
                  video.conversion_status === "converting" ||
                  (isBulkCurrent && video.conversion_status !== "converted"));
              return (
                <TableRow key={video.filename} className="odd:bg-muted/30">
                  <TableCell>
                    {availableVideo?.path ? (
                      <a
                        className="font-medium underline underline-offset-4"
                        href={`/assets/videos/input/${availableVideo.path}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {video.filename}
                      </a>
                    ) : (
                      <span className="font-medium">{video.filename}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {availableVideo
                      ? `${availableVideo.width}x${availableVideo.height}`
                      : "-"}
                  </TableCell>
                  <TableCell>{availableVideo?.codec ?? "-"}</TableCell>
                  <TableCell>
                    {availableVideo
                      ? formatElapsedTimeSeconds(availableVideo.duration)
                      : "-"}
                  </TableCell>
                  <TableCell>
                    {availableVideo?.source === "uploaded" ? (
                      <Badge variant="secondary">Uploaded</Badge>
                    ) : isConverting ? (
                      <Badge variant="secondary">
                        <Loader2 className="animate-spin" />
                        Converting
                      </Badge>
                    ) : isDownloaded ? (
                      <Badge variant="success">Downloaded</Badge>
                    ) : isDownloading ? (
                      <Badge variant="secondary">
                        <Loader2 className="animate-spin" />
                        Downloading
                      </Badge>
                    ) : hasNameConflict ? (
                      <Badge variant="destructive">Name conflict</Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isBulkProcessing}
                        onClick={() => handleDownload(video.filename)}
                      >
                        <Download className="size-4" />
                        {video.status === "failed"
                          ? SAMPLE_DOWNLOAD_LABELS.failed
                          : SAMPLE_DOWNLOAD_LABELS.available}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {filteredVideos
              .filter((video) => !sampleFilenames.has(video.filename))
              .map((video) => (
                <TableRow key={video.filename} className="odd:bg-muted/30">
                  <TableCell className="font-medium">
                    {video.path ? (
                      <a
                        className="underline underline-offset-4"
                        href={`/assets/videos/input/${video.path}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {video.filename}
                      </a>
                    ) : (
                      video.filename
                    )}
                  </TableCell>
                  <TableCell>
                    {video.width}x{video.height}
                  </TableCell>
                  <TableCell>{video.codec}</TableCell>
                  <TableCell>
                    {formatElapsedTimeSeconds(video.duration)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        video.source !== "uploaded" && video.codec === "h265"
                          ? "success"
                          : "secondary"
                      }
                    >
                      {video.source === "uploaded"
                        ? "Uploaded"
                        : video.codec === "h265"
                          ? "Downloaded"
                          : "Available"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </section>
    </div>
  );
};
