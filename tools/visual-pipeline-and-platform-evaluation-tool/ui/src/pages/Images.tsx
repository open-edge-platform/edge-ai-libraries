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
  const dispatch = useAppDispatch();
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
        // TODO: Implement image exists check when API is available
        return { exists: false };
      } catch (error) {
        console.error(`Error checking file ${filename}:`, error);
        return { exists: false };
      }
    },
    [],
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
        // TODO: Invalidate images cache when API is available
        // dispatch(api.util.invalidateTags(["images"]));
        toast.success("Upload completed.");
      } else if (succeeded > 0 && failed > 0) {
        toast.warning(
          `${succeeded} file(s) uploaded successfully. ${failed} failed.`,
        );
        // dispatch(api.util.invalidateTags(["images"]));
      } else if (failed > 0) {
        toast.error(`Upload failed for ${failed} file(s).`);
      }
    },
    [dispatch],
  );

  // TODO: Replace with actual API query when available
  const images: any[] = [];
  const isLoading = false;

  if (isLoading) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">Loading images...</div>
      </div>
    );
  }

  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Images</h1>
        <p className="text-muted-foreground mt-2">
          Ready-to-use images available in the platform
        </p>
      </div>

      <MultiFileUploader
        accept="image/*"
        uploadEndpoint="/api/images/upload"
        checkFileExists={handleCheckFileExists}
        onUploadProgress={handleUploadProgress}
        onUploadComplete={handleUploadComplete}
        multiple={true}
        maxConcurrentUploads={3}
        className="mb-8"
      />

      {images.length > 0 ? (
        <Table>
          <TableCaption>A list of loaded images.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[25%]">File name</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Format</TableHead>
              <TableHead>Preview</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {images.map((image: any) => (
              <TableRow key={image.filename}>
                <TableCell className="font-medium">{image.filename}</TableCell>
                <TableCell>
                  {image.width}x{image.height}
                </TableCell>
                <TableCell>{image.format}</TableCell>
                <TableCell>
                  <img
                    src={`/assets/images/input/${image.filename}`}
                    alt={image.filename}
                    className="w-48 h-auto"
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div className="text-center py-10 text-muted-foreground">
          No images uploaded yet. Upload your first image above.
        </div>
      )}
    </div>
  );
};
