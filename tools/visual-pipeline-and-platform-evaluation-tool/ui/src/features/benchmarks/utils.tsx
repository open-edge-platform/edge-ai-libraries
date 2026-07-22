import type { ExportBenchmarkSuiteRunCsvDownload } from "@/api/apiEnhancements";
import { Badge } from "@/components/ui/badge";
import { downloadResponseAsFile } from "@/lib/fileUtils";
import { formatFilenameTimestamp } from "@/lib/pdfUtils";

export const formatBenchmarkScore = (value: number | null | undefined) => {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(2);
};

export const renderBenchmarkStatus = (status: string) => {
  if (status === "passed") {
    return <Badge variant="success">Passed</Badge>;
  }
  if (status === "created") {
    return <Badge variant="outline">Queued</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">Failed</Badge>;
  }
  if (status === "running") {
    return (
      <span className="animate-pulse text-benchmark-status-running">
        running
      </span>
    );
  }
  if (status === "cancelled") {
    return <Badge variant="outline">Cancelled</Badge>;
  }
  return <span className="text-muted-foreground">{status}</span>;
};

const exportBenchmarkRunCsv = async (
  response: ExportBenchmarkSuiteRunCsvDownload,
  filename: string,
) => {
  const headers = new Headers();
  if (response.contentDisposition) {
    headers.set("content-disposition", response.contentDisposition);
  }
  if (response.contentType) {
    headers.set("content-type", response.contentType);
  }
  await downloadResponseAsFile(
    new Response(response.blob, { headers }),
    filename,
  );
};

export { exportBenchmarkRunCsv };

export const formatBenchmarkExportFilename = (
  slug: string,
  startTime: number,
  extension: string,
) => `${slug}-results-${formatFilenameTimestamp(startTime)}.${extension}`;
