// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  api,
  useDownloadSampleAudioRecordingVoiceSampleRecordingsFilenameDownloadPostMutation,
  useListSampleAudioRecordingsVoiceSampleRecordingsGetQuery,
} from "@/api/api.generated.ts";
import { Badge } from "@/components/ui/badge.tsx";
import { Button } from "@/components/ui/button.tsx";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { useAppDispatch } from "@/store/hooks";
import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

export const Audio = () => {
  const {
    data: recordings = [],
    isLoading,
    isError,
  } = useListSampleAudioRecordingsVoiceSampleRecordingsGetQuery();
  const [downloadSample] =
    useDownloadSampleAudioRecordingVoiceSampleRecordingsFilenameDownloadPostMutation();
  const dispatch = useAppDispatch();
  const [downloadingFilename, setDownloadingFilename] = useState<string | null>(
    null,
  );
  const [isDownloadingAll, setIsDownloadingAll] = useState(false);

  const remainingFilenames = recordings
    .filter((recording) => !recording.downloaded)
    .map((recording) => recording.filename);

  const downloadToServer = async (filename: string): Promise<boolean> => {
    setDownloadingFilename(filename);
    try {
      const sample = await downloadSample({ filename }).unwrap();
      // Mark the row immediately instead of waiting for the list refetch.
      dispatch(
        api.util.updateQueryData(
          "listSampleAudioRecordingsVoiceSampleRecordingsGet",
          undefined,
          (draft) => {
            const row = draft.find((item) => item.filename === filename);
            if (row) row.downloaded = sample.downloaded;
          },
        ),
      );
      return true;
    } catch {
      return false;
    } finally {
      setDownloadingFilename(null);
    }
  };

  const handleDownload = async (filename: string) => {
    if (await downloadToServer(filename)) {
      toast.success(`${filename} downloaded.`);
    } else {
      toast.error(`Could not download ${filename}.`);
    }
  };

  const handleDownloadAll = async () => {
    const filenames = remainingFilenames;
    setIsDownloadingAll(true);
    let failed = 0;
    try {
      for (const filename of filenames) {
        if (!(await downloadToServer(filename))) failed += 1;
      }
    } finally {
      setIsDownloadingAll(false);
    }
    if (failed > 0) {
      toast.warning(
        `${filenames.length - failed} recording(s) downloaded; ${failed} failed.`,
      );
    } else {
      toast.success(`${filenames.length} recording(s) downloaded.`);
    }
  };

  if (isLoading) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">
          Loading audio recordings...
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">
          Could not load audio recordings.
        </div>
      </div>
    );
  }

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Audio</h1>
        <p className="mt-2 text-muted-foreground">
          American English sample recordings. Downloaded recordings become
          available as input for the Speech to Text pipeline.
        </p>
      </div>

      <div className="sticky top-0 z-10 mb-3 flex items-center justify-end gap-3 border-b bg-background py-3">
        <Button
          size="sm"
          disabled={
            remainingFilenames.length === 0 ||
            isDownloadingAll ||
            downloadingFilename !== null
          }
          onClick={handleDownloadAll}
        >
          {isDownloadingAll ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Download className="size-4" />
          )}
          {isDownloadingAll
            ? `Downloading ${downloadingFilename ?? "recordings"}...`
            : recordings.length > 0 && remainingFilenames.length === 0
              ? "All downloaded"
              : `Download all (${remainingFilenames.length})`}
        </Button>
      </div>

      <div className="mb-4 border-l-4 border-primary bg-muted/40 px-4 py-3 text-sm">
        <p>
          Source:{" "}
          <a
            className="font-medium text-foreground underline underline-offset-4"
            href="https://www.voiptroubleshooter.com/open_speech/american.html"
            target="_blank"
            rel="noreferrer"
          >
            Open Speech Repository
          </a>
          .
        </p>
        <p className="mt-1 text-muted-foreground">
          The recordings are available for reasonable use with source
          attribution.
        </p>
      </div>

      {recordings.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File name</TableHead>
              <TableHead>M/F</TableHead>
              <TableHead>Format</TableHead>
              <TableHead>Sample rate</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {recordings.map((recording) => (
              <TableRow key={recording.filename} className="odd:bg-muted/30">
                <TableCell className="font-medium">
                  {recording.filename}
                </TableCell>
                <TableCell>{recording.gender}</TableCell>
                <TableCell>{recording.format}</TableCell>
                <TableCell>{recording.sample_rate}</TableCell>
                <TableCell>{recording.description}</TableCell>
                <TableCell>
                  {recording.downloaded ? (
                    <Badge variant="success">Downloaded</Badge>
                  ) : downloadingFilename === recording.filename ? (
                    <Badge variant="secondary" className="gap-2">
                      <Loader2 className="size-3 animate-spin" />
                      Downloading
                    </Badge>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        isDownloadingAll || downloadingFilename !== null
                      }
                      onClick={() => void handleDownload(recording.filename)}
                    >
                      <Download className="size-4" />
                      Download
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div className="py-10 text-center text-muted-foreground">
          No audio recordings available.
        </div>
      )}
    </div>
  );
};
