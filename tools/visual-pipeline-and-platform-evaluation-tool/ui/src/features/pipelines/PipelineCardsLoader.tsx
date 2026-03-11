import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardHeader } from "@/components/ui/card";

type PipelineCardsLoaderProps = {
  count?: number;
};

export const PipelineCardsLoader = ({
  count = 5,
}: PipelineCardsLoaderProps) => {
  return (
    <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(300px,1fr))]">
      {Array.from({ length: count }).map((_, i) => (
        <Card key={i} className="flex flex-col pt-0 overflow-hidden">
          <Skeleton className="w-full h-48" />
          <CardHeader className="space-y-2">
            <Skeleton className="h-7 w-3/4" />
            <div className="flex flex-wrap gap-1">
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-6 w-14" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          </CardHeader>
        </Card>
      ))}
    </div>
  );
};
