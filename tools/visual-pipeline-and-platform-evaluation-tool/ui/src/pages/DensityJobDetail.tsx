import { useParams, Link } from "react-router";
import { useGetDensityJobStatusQuery } from "@/api/api.generated";

export const DensityJobDetail = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const {
    data: jobStatus,
    isLoading,
    error,
  } = useGetDensityJobStatusQuery(
    { jobId: jobId! },
    {
      pollingInterval: 2000,
      skip: !jobId,
    },
  );

  return (
    <div className="container mx-auto py-10">
      <div className="mb-6">
        <Link
          to="/jobs/density"
          className="text-sm text-muted-foreground hover:text-foreground mb-2 inline-block"
        >
          ← Back to Density Jobs
        </Link>
        <h1 className="text-3xl font-bold">Density Job Details</h1>
        <p className="text-muted-foreground mt-2">Job ID: {jobId}</p>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading job details...</p>
      ) : error ? (
        <div className="p-4 border border-red-500 bg-red-50 dark:bg-red-950">
          <p className="text-red-800 dark:text-red-200">
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
  );
};
