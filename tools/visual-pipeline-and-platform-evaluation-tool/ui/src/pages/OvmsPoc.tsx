// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { Film, Gauge, Play, Square } from "lucide-react";
import { useGetVideosQuery } from "@/api/api.generated";
import {
  useGetOvmsPocJobQuery,
  useGetOvmsPocMetadataQuery,
  useRunOvmsPocMutation,
  useStopOvmsPocJobMutation,
  type OvmsPocStatus,
} from "@/api/ovmsPocApi";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { handleApiError } from "@/lib/apiUtils";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { filterOutTransportStreams } from "@/lib/videoUtils";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard";
import { useActiveJobSync } from "@/hooks/useActiveJobSync";

const statusVariant = (state: OvmsPocStatus["state"]) => {
  if (state === "COMPLETED") return "success";
  if (state === "FAILED") return "destructive";
  if (state === "RUNNING" || state === "STARTING") return "secondary";
  return "outline";
};

const publicVideoUrl = (outputVideo?: string) =>
  outputVideo?.startsWith("/videos/") ? `/assets${outputVideo}` : undefined;

export const OvmsPoc = () => {
  const { data: videos = [] } = useGetVideosQuery();
  const inputVideos = filterOutTransportStreams(videos).filter(
    (video): video is typeof video & { path: string } => Boolean(video.path),
  );
  const [inputVideo, setInputVideo] = useState("auto/obj_classification.mp4");
  const [parallelRequests, setParallelRequests] = useState("2");
  const [jobId, setJobId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  useActiveJobSync(jobId);
  const [runOvmsPoc, { isLoading: isStarting }] = useRunOvmsPocMutation();
  const [stopOvmsPocJob, { isLoading: isStopping }] =
    useStopOvmsPocJobMutation();
  const { data: status } = useGetOvmsPocJobQuery(jobId ?? "", {
    skip: !jobId,
    pollingInterval: jobId ? 1500 : 0,
  });
  const { data: metadata = [] } = useGetOvmsPocMetadataQuery(jobId ?? "", {
    skip: !jobId,
    pollingInterval: status?.state === "RUNNING" ? 3000 : 0,
  });
  const running = status?.state === "STARTING" || status?.state === "RUNNING";
  const outputUrl = publicVideoUrl(status?.output_video);

  const run = async () => {
    setErrorMessage(null);
    try {
      const result = await runOvmsPoc({
        input_video: inputVideo,
        max_parallel_requests: Number(parallelRequests),
      }).unwrap();
      setJobId(result.job_id);
    } catch (error) {
      setErrorMessage(handleApiError(error, "Could not start OVMS POC"));
    }
  };

  const stop = async () => {
    if (!jobId) return;
    try {
      await stopOvmsPocJob(jobId).unwrap();
    } catch (error) {
      setErrorMessage(handleApiError(error, "Could not stop OVMS POC"));
    }
  };

  return (
    <div className={`${CONTENT_CONTAINER_CLASS} space-y-6`}>
      <div>
        <h1 className="text-3xl font-bold">OVMS POC</h1>
        <p className="text-sm text-muted-foreground">
          File-to-file KServe gRPC streaming through OpenVINO Model Server.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Run configuration</CardTitle>
          <CardDescription>
            Select an uploaded or bundled video and run the public detection and
            classification stream in OVMS.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-[minmax(0,1fr)_11rem_auto] md:items-end">
          <div className="grid gap-2">
            <Label htmlFor="ovms-input-video">Input video</Label>
            <Select
              value={inputVideo}
              onValueChange={setInputVideo}
              disabled={running || isStarting}
            >
              <SelectTrigger id="ovms-input-video">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {inputVideos.map((video) => (
                  <SelectItem key={video.path} value={video.path}>
                    {video.path}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="ovms-parallel-requests">Parallel requests</Label>
            <Input
              id="ovms-parallel-requests"
              type="number"
              min="1"
              max="8"
              value={parallelRequests}
              onChange={(event) => setParallelRequests(event.target.value)}
              disabled={running || isStarting}
            />
          </div>
          {running ? (
            <Button
              variant="destructive"
              onClick={stop}
              disabled={isStopping}
              title="Stop OVMS POC"
            >
              <Square /> Stop
            </Button>
          ) : (
            <Button
              onClick={run}
              disabled={isStarting || !inputVideo}
              title="Run OVMS POC"
            >
              <Play /> Run POC
            </Button>
          )}
        </CardContent>
      </Card>

      {errorMessage && (
        <p className="text-sm text-destructive">{errorMessage}</p>
      )}

      {status && (
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Job {status.job_id}</CardTitle>
              <CardDescription>
                KServe gRPC stream executed through OVMS.
              </CardDescription>
            </div>
            <Badge variant={statusVariant(status.state)}>{status.state}</Badge>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4 text-sm md:grid-cols-5">
            <div>
              <p className="text-muted-foreground">Frames</p>
              <p className="font-medium">{status.frames_processed ?? 0}</p>
            </div>
            <div>
              <p className="text-muted-foreground">E2E FPS</p>
              <p className="font-medium">
                {(status.end_to_end_fps ?? status.fps ?? 0).toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">OVMS FPS</p>
              <p className="font-medium">
                {status.ovms_fps?.toFixed(2) ?? "-"}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Mean OVMS</p>
              <p className="font-medium">
                {status.mean_ovms_inference_ms?.toFixed(1) ?? "-"} ms
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Failed frames</p>
              <p className="font-medium">{status.failed_frames ?? 0}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {jobId && (
        <Tabs defaultValue="output">
          <TabsList>
            <TabsTrigger value="output">
              <Film /> Output video
            </TabsTrigger>
            <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
            <TabsTrigger value="performance">
              <Gauge /> Performance
            </TabsTrigger>
          </TabsList>
          <TabsContent value="output" className="pt-4">
            {outputUrl ? (
              <video
                controls
                className="w-full max-w-4xl border"
                src={outputUrl}
              >
                Your browser does not support the video tag.
              </video>
            ) : (
              <p className="text-sm text-muted-foreground">
                Output video will be available when the job completes.
              </p>
            )}
          </TabsContent>
          <TabsContent value="metadata" className="pt-4">
            {metadata.length ? (
              <pre className="max-h-[32rem] overflow-auto border bg-muted p-4 text-xs">
                {JSON.stringify(metadata, null, 2)}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">
                Waiting for prediction metadata.
              </p>
            )}
          </TabsContent>
          <TabsContent value="performance" className="pt-4">
            <MetricsDashboard enableLatencyMetrics />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
};
