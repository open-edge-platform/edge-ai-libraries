// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  useGetDefaultVideoRecordingsQuery,
  useGetVideosQuery,
  useStartDefaultVideoDownloadMutation,
} from "@/api/api.generated.ts";
import { useAppDispatch } from "@/store/hooks.ts";
import { toast } from "@/lib/toast";

export type PipelineVideoStatus =
  "downloaded" | "not_downloaded" | "downloading" | "failed" | "conflict";

export type PipelineVideoStatusItem = {
  filename: string;
  status: PipelineVideoStatus;
  downloadable: boolean;
};

const SAMPLE_POLL_INTERVAL_MS = 2000;

type UseRequiredVideosStatusOptions = {
  skip?: boolean;
};

export const useRequiredVideosStatus = (
  requiredVideos: readonly string[],
  { skip = false }: UseRequiredVideosStatusOptions = {},
) => {
  const dispatch = useAppDispatch();
  const [trackedDownloads, setTrackedDownloads] = useState<string[]>([]);
  const [startingDownloads, setStartingDownloads] = useState<string[]>([]);
  const shouldSkip = skip || requiredVideos.length === 0;

  const { data: videos, isSuccess: videosLoaded } = useGetVideosQuery(
    undefined,
    { skip: shouldSkip },
  );
  const {
    data: sampleVideos,
    isSuccess: samplesLoaded,
    refetch: refetchSampleVideos,
  } = useGetDefaultVideoRecordingsQuery(undefined, {
    skip: shouldSkip,
    pollingInterval: trackedDownloads.length > 0 ? SAMPLE_POLL_INTERVAL_MS : 0,
  });
  const [startDefaultVideoDownload] = useStartDefaultVideoDownloadMutation();

  const videoStatuses = useMemo<PipelineVideoStatusItem[]>(() => {
    if (shouldSkip || !videosLoaded || !samplesLoaded) return [];
    const availableVideos = new Set(
      (videos ?? []).map((video) => video.filename),
    );
    const samplesByFilename = new Map(
      (sampleVideos ?? []).map((sample) => [sample.filename, sample]),
    );

    return requiredVideos.map((filename): PipelineVideoStatusItem => {
      if (availableVideos.has(filename)) {
        return { filename, status: "downloaded", downloadable: false };
      }
      const sample = samplesByFilename.get(filename);
      if (!sample) {
        return { filename, status: "not_downloaded", downloadable: false };
      }
      if (
        startingDownloads.includes(filename) ||
        trackedDownloads.includes(filename) ||
        sample.status === "queued" ||
        sample.status === "downloading"
      ) {
        return { filename, status: "downloading", downloadable: false };
      }
      if (sample.status === "downloaded") {
        return { filename, status: "downloaded", downloadable: false };
      }
      if (sample.status === "failed") {
        return { filename, status: "failed", downloadable: true };
      }
      if (sample.status === "conflict") {
        return { filename, status: "conflict", downloadable: false };
      }
      return { filename, status: "not_downloaded", downloadable: true };
    });
  }, [
    requiredVideos,
    sampleVideos,
    samplesLoaded,
    shouldSkip,
    startingDownloads,
    trackedDownloads,
    videos,
    videosLoaded,
  ]);

  // Follow downloads started elsewhere (e.g. on the Videos page) as well.
  useEffect(() => {
    if (!sampleVideos) return;
    const inProgress = sampleVideos
      .filter(
        (sample) =>
          requiredVideos.includes(sample.filename) &&
          (sample.status === "queued" || sample.status === "downloading"),
      )
      .map((sample) => sample.filename)
      .filter((filename) => !trackedDownloads.includes(filename));
    if (inProgress.length > 0) {
      setTrackedDownloads((current) => [
        ...new Set([...current, ...inProgress]),
      ]);
    }
  }, [requiredVideos, sampleVideos, trackedDownloads]);

  useEffect(() => {
    if (!sampleVideos || trackedDownloads.length === 0) return;
    const finished = trackedDownloads.filter((filename) =>
      ["downloaded", "failed", "conflict", "available"].includes(
        sampleVideos.find((sample) => sample.filename === filename)?.status ??
          "",
      ),
    );
    if (finished.length === 0) return;

    setTrackedDownloads((current) =>
      current.filter((filename) => !finished.includes(filename)),
    );
    dispatch(api.util.invalidateTags(["videos"]));
    finished.forEach((filename) => {
      const status = sampleVideos.find(
        (sample) => sample.filename === filename,
      )?.status;
      if (status === "downloaded") {
        toast.success(`Video ${filename} downloaded`);
      } else {
        toast.error(`Could not download video ${filename}`);
      }
    });
  }, [dispatch, sampleVideos, trackedDownloads]);

  const downloadVideo = useCallback(
    async (filename: string) => {
      setStartingDownloads((current) => [...new Set([...current, filename])]);
      try {
        await startDefaultVideoDownload({
          defaultVideoDownloadRequest: { filename },
        }).unwrap();
        // Refresh first so tracking never sees the pre-download "available" status.
        await refetchSampleVideos();
        setTrackedDownloads((current) => [...new Set([...current, filename])]);
      } catch {
        toast.error(`Could not start downloading video ${filename}`);
      } finally {
        setStartingDownloads((current) =>
          current.filter((name) => name !== filename),
        );
      }
    },
    [refetchSampleVideos, startDefaultVideoDownload],
  );

  const missingVideos = useMemo(
    () => videoStatuses.filter((item) => item.status !== "downloaded"),
    [videoStatuses],
  );

  return {
    videoStatuses,
    missingVideos,
    hasMissingVideos: missingVideos.length > 0,
    downloadVideo,
  };
};
