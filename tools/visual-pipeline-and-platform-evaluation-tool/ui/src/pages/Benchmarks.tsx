import { useGetBenchmarksQuery } from "@/api/api.generated";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Trophy } from "lucide-react";
export const Benchmarks = () => {
  const { data: benchmarks, isLoading, error } = useGetBenchmarksQuery();
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-6">
          <Trophy className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Benchmarks</h1>
        </div>
        <div className="grid gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-6 w-48" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-6">
          <Trophy className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Benchmarks</h1>
        </div>
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive text-center">
              Failed to load benchmarks. Please try again later.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-6">
        <Trophy className="h-6 w-6" />
        <h1 className="text-2xl font-bold">Benchmarks</h1>
      </div>
      {!benchmarks || benchmarks.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-muted-foreground text-center">
              No benchmarks available.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {benchmarks.map((benchmark) => (
            <Card key={benchmark.id} className="flex flex-col">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{benchmark.name}</CardTitle>
                  <Badge variant="outline" className="capitalize">
                    {benchmark.type}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="flex-1">
                <div className="space-y-4">
                  <div>
                    <h4 className="text-sm font-medium mb-2">Setups:</h4>
                    <div className="space-y-2">
                      {benchmark.setups.map((setup, idx) => (
                        <div
                          key={idx}
                          className="p-3 bg-muted/50 rounded-md text-sm"
                        >
                          <div className="space-y-1.5">
                            <div>
                              <span className="text-muted-foreground">
                                Pipeline:
                              </span>{" "}
                              <span className="font-mono text-xs">
                                {setup.pipeline_id}
                              </span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">
                                Variant:
                              </span>{" "}
                              <span className="font-mono text-xs">
                                {setup.variant_id}
                              </span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">
                                {benchmark.type === "performance"
                                  ? "Streams:"
                                  : "Participation Rate:"}
                              </span>{" "}
                              <span className="font-medium">
                                {"streams" in setup
                                  ? setup.streams
                                  : `${setup.participation_rate}%`}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
