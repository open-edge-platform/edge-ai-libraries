import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { GitCompareArrows, X } from "lucide-react";

type CompareBarProps = {
  count: number;
  limit: number;
  compareTo: string;
  onClear: () => void;
};

/** Sticky action bar that appears once results are selected for comparison. */
export const CompareBar = ({
  count,
  limit,
  compareTo,
  onClear,
}: CompareBarProps) => {
  if (count === 0) return null;

  return (
    <div className="sticky bottom-4 z-10 mt-4 flex justify-center">
      <div className="flex items-center gap-4 rounded-full border bg-card px-5 py-2 shadow-lg">
        <span className="text-sm">
          <span className="font-semibold">{count}</span> of {limit} selected
        </span>
        <Button variant="ghost" size="sm" onClick={onClear}>
          <X className="h-4 w-4" />
          Clear
        </Button>
        <Button asChild size="sm" disabled={count < 1}>
          <Link to={compareTo}>
            <GitCompareArrows className="h-4 w-4" />
            Compare
          </Link>
        </Button>
      </div>
    </div>
  );
};
