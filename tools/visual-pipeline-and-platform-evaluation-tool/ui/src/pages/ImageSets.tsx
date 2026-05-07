import {
  api,
  useGetImageSetsQuery,
  useLazyCheckImageSetExistsQuery,
} from "@/api/api.generated.ts";
import { ENDPOINTS } from "@/api/apiEndpoints";
import { useEffect, useCallback } from "react";
import { useAppDispatch } from "@/store/hooks";
import { toast } from "sonner";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { MultiFileUploader } from "@/features/upload/MultiFileUploader.tsx";
import { Folder } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card.tsx";
import { Link } from "react-router";

export const ImageSets = () => {
  const { data: imageSets, isSuccess, isLoading } = useGetImageSetsQuery();
  const dispatch = useAppDispatch();
  const [checkImageSetExists] = useLazyCheckImageSetExistsQuery();
  const { registerJobGroup, unregisterJobGroup, updateJobs } =
    useBackgroundJobs();

  // Register this component as a job group
  useEffect(() => {
    registerJobGroup("images", "Image Uploads", ["/images"]);
    return () => {
      unregisterJobGroup("images");
    };
  }, [registerJobGroup, unregisterJobGroup]);

  const handleCheckFileExists = useCallback(
    async (filename: string): Promise<{ exists: boolean }> => {
      try {
        // Extract name without extension for image set directory check
        const name = filename.replace(/\.(zip|tar|tar\.gz|tgz)$/i, "");
        const result = await checkImageSetExists({ name }).unwrap();
        return { exists: result.exists };
      } catch (error) {
        console.error(`Error checking file ${filename}:`, error);
        return { exists: false };
      }
    },
    [checkImageSetExists],
  );

  const handleUploadProgress = useCallback(
    (jobs: Array<{ id: string; name: string; progress: number }>) => {
      updateJobs("images", jobs);
    },
    [updateJobs],
  );

  const handleUploadComplete = useCallback(
    (succeeded: number, failed: number) => {
      if (failed === 0 && succeeded > 0) {
        dispatch(api.util.invalidateTags(["images"]));
        toast.success("Upload completed.");
      } else if (succeeded > 0 && failed > 0) {
        toast.warning(
          `${succeeded} file(s) uploaded successfully. ${failed} failed.`,
        );
        dispatch(api.util.invalidateTags(["images"]));
      } else if (failed > 0) {
        toast.error(`Upload failed for ${failed} file(s).`);
      }
    },
    [dispatch],
  );

  if (isLoading) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">Loading image sets...</div>
      </div>
    );
  }

  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Images</h1>
        <p className="text-muted-foreground mt-2">
          Upload archive files (.zip, .tar, .tar.gz, .tgz) to extract and use
          image sets
        </p>
      </div>

      <MultiFileUploader
        accept=".zip,.tar,.tar.gz,.tgz,application/zip,application/x-tar,application/gzip,application/x-gzip"
        maxSize={2 * 1024 * 1024 * 1024} // 2 GB
        uploadEndpoint={ENDPOINTS.UPLOAD_IMAGE_ARCHIVE}
        checkFileExists={handleCheckFileExists}
        onUploadProgress={handleUploadProgress}
        onUploadComplete={handleUploadComplete}
        multiple={true}
        maxConcurrentUploads={3}
        className="mb-8"
      />

      {isSuccess && imageSets && imageSets.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {imageSets.map((imageSet) => (
            <Link key={imageSet.name} to={`/images/${imageSet.name}`}>
              <Card className="transition-all duration-200 overflow-hidden cursor-pointer hover:-translate-y-1 hover:shadow-md">
                <CardContent className="flex flex-col items-center justify-center p-6">
                  <Folder className="w-16 h-16 text-primary mb-3" />
                  <div className="text-center">
                    <p className="font-medium text-sm wrap-break-word">
                      {imageSet.name}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {imageSet.image_count}{" "}
                      {imageSet.image_count === 1 ? "image" : "images"}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <div className="text-center py-10 text-muted-foreground">
          No image sets uploaded yet. Upload your first archive above.
        </div>
      )}
    </div>
  );
};
