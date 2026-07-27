import type {
  BenchmarkSuite,
  BenchmarkSuiteRunDetails,
} from "@/api/api.generated.ts";
import {
  type ExportBenchmarkSuiteRunCsvDownload,
  useLazyExportBenchmarkSuiteRunCsvQuery,
} from "@/api/apiEnhancements";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { exportNodeToPdf } from "@/lib/pdfUtils";
import { toast } from "@/lib/toast";
import { BookOpenText, FileDigit } from "lucide-react";
import { useTheme } from "next-themes";
import { useState } from "react";
import { exportBenchmarkRunCsv, formatBenchmarkExportFilename } from "./utils";

type BenchmarkExportButtonProps = {
  benchmark: BenchmarkSuite;
  runDetails: BenchmarkSuiteRunDetails;
  isDisabled?: boolean;
};

const EXPORT_NODE_ID = "benchmark-results-export";

export const BenchmarkExportButton = ({
  benchmark,
  runDetails,
  isDisabled = false,
}: BenchmarkExportButtonProps) => {
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);

  const { theme } = useTheme();
  const [triggerExportCsv] = useLazyExportBenchmarkSuiteRunCsvQuery();
  const isExporting = isExportingPdf || isExportingCsv;

  const handleExportPdf = async () => {
    const node = document.getElementById(EXPORT_NODE_ID);
    if (!node) {
      return;
    }

    try {
      setIsExportingPdf(true);
      await exportNodeToPdf({
        filename: formatBenchmarkExportFilename(
          benchmark.slug,
          runDetails.start_time,
          "pdf",
        ),
        node,
        isDarkMode: theme === "dark",
      });
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleCsvExport = async () => {
    try {
      setIsExportingCsv(true);
      const filename = formatBenchmarkExportFilename(
        runDetails.suite_slug,
        runDetails.start_time,
        "csv",
      );
      const response: ExportBenchmarkSuiteRunCsvDownload =
        await triggerExportCsv({
          suiteSlug: runDetails.suite_slug,
          runId: runDetails.id,
        }).unwrap();
      await exportBenchmarkRunCsv(response, filename);
    } catch {
      toast.error("Failed to export CSV for this run.");
    } finally {
      setIsExportingCsv(false);
    }
  };

  if (runDetails.status !== "passed") {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          className="gap-2"
          disabled={isDisabled || isExporting}
          data-export-ignore
        >
          {isExporting ? "Exporting..." : "Export Results"}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" data-export-ignore>
        <DropdownMenuItem
          disabled={isExporting}
          onSelect={() => {
            void handleExportPdf();
          }}
        >
          <BookOpenText className="mr-2 h-4 w-4" />
          {isExportingPdf ? "Exporting PDF..." : "Export to PDF"}
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={isExporting}
          onSelect={() => {
            void handleCsvExport();
          }}
        >
          <FileDigit className="mr-2 h-4 w-4" />
          {isExportingCsv ? "Exporting CSV..." : "Export to CSV"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
