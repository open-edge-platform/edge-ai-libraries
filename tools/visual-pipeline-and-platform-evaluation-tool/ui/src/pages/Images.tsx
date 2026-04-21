import {
  api,
  useGetImageSetsQuery,
  useLazyCheckImageSetExistsQuery,
} from "@/api/api.generated.ts";
import { ENDPOINTS } from "@/api/apiEndpoints";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { useEffect, useCallback } from "react";
import { useAppDispatch } from "@/store/hooks";
import { toast } from "sonner";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { MultiFileUploader } from "@/components/shared/MultiFileUploader.tsx";

export const Images = () => {
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
        const name = filename.replace(
          /\.(zip|tar|tar\.gz|tgz|tar\.bz2|tbz2)$/i,
          "",
        );
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
          Upload archive files to extract and use image sets
        </p>
      </div>

      <MultiFileUploader
        accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2,.tbz2,application/zip,application/x-tar,application/gzip,application/x-gzip,application/x-bzip2"
        uploadEndpoint={ENDPOINTS.UPLOAD_IMAGE_ARCHIVE}
        checkFileExists={handleCheckFileExists}
        onUploadProgress={handleUploadProgress}
        onUploadComplete={handleUploadComplete}
        multiple={true}
        maxConcurrentUploads={3}
        className="mb-8"
      />

      {isSuccess && imageSets && imageSets.length > 0 ? (
        <Table>
          <TableCaption>A list of loaded image sets.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[50%]">Image Set Name</TableHead>
              <TableHead>Number of Images</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {imageSets.map((imageSet) => (
              <TableRow key={imageSet.name}>
                <TableCell className="font-medium">{imageSet.name}</TableCell>
                <TableCell>{imageSet.image_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div className="text-center py-10 text-muted-foreground">
          No image sets uploaded yet. Upload your first archive above.
        </div>
      )}
    </div>
  );
};
