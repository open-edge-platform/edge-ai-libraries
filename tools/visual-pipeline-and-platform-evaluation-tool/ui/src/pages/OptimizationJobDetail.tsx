import { useParams, Link } from "react-router";
import { useGetOptimizationJobStatusQuery } from "@/api/api.generated";

export const OptimizationJobDetail = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const {
    data: jobStatus,
    isLoading,
    error,
  } = useGetOptimizationJobStatusQuery(
    { jobId: jobId! },
    {
      pollingInterval: 2000,
      skip: !jobId,
    },
  );

  return (
    <>
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <Link
            to="/jobs/optimize"
            className="text-sm text-muted-foreground hover:text-foreground mb-2 inline-block"
          >
            ← Back to Optimization Jobs
          </Link>
          <h1 className="text-3xl font-bold">Optimization Job Details</h1>
          <p className="text-muted-foreground mt-2">Job ID: {jobId}</p>
        </div>

        {isLoading ? (
          <p className="text-muted-foreground">Loading job details...</p>
        ) : error ? (
          <div className="status-error p-4 border border-status-border bg-status-bg">
            <p className="text-status-fg">
              Error loading job details
            </p>
          </div>
        ) : (
          <div className="border p-6">
            <pre className="whitespace-pre-wrap break-words text-sm">
              {JSON.stringify(jobStatus, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </>
  );
};
