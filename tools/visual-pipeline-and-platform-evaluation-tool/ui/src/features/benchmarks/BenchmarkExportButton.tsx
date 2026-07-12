import type {
  BenchmarkSuite,
  BenchmarkSuiteRunDetails,
} from "@/api/api.generated.ts";
import { Button } from "@/components/ui/button";
import { exportNodeToPdf, formatFilenameTimestamp } from "@/lib/pdfUtils";
import { FileUp } from "lucide-react";
import { useTheme } from "next-themes";
import { useState } from "react";

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
  const [isExporting, setIsExporting] = useState(false);

  const { theme } = useTheme();

  const handleExportPdf = async () => {
    const node = document.getElementById(EXPORT_NODE_ID);
    if (!node) {
      return;
    }

    try {
      setIsExporting(true);
      const startTimeLabel = formatFilenameTimestamp(runDetails.start_time);
      await exportNodeToPdf({
        filename: `${benchmark.slug}-results-${startTimeLabel}.pdf`,
        node,
        isDarkMode: theme === "dark",
      });
    } finally {
      setIsExporting(false);
    }
  };

  if (runDetails.status !== "passed") {
    return null;
  }

  return (
    <Button
      type="button"
      className="gap-2"
      onClick={handleExportPdf}
      disabled={isDisabled || isExporting}
      data-export-ignore
    >
      <FileUp className="h-4 w-4" />
      {isExporting ? "Exporting..." : "Export Results"}
    </Button>
  );
};
