import {
  useGetVideosQuery,
  api,
  useLazyCheckVideoInputExistsQuery,
} from "@/api/api.generated.ts";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { formatElapsedTimeSeconds } from "@/lib/timeUtils.ts";
import { filterOutTransportStreams } from "@/lib/videoUtils.ts";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Label } from "@/components/ui/label.tsx";
import { useState, useRef } from "react";
import { Upload, X, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress.tsx";
import { useAppDispatch } from "@/store/hooks";

type UploadFormData = {
  files: FileList | null;
};

type FileUploadState = {
  file: File;
  status: "pending" | "uploading" | "completed" | "failed";
  progress: number;
  error?: string;
};

const MAX_CONCURRENT_UPLOADS = 3;

export const Videos = () => {
  const { data: videos, isSuccess } = useGetVideosQuery();
  const dispatch = useAppDispatch();
  const [checkVideoExists] = useLazyCheckVideoInputExistsQuery();
  const { register, handleSubmit, reset, watch, setValue } =
    useForm<UploadFormData>({
      defaultValues: {
        files: null,
      },
    });

  const [isDragging, setIsDragging] = useState(false);
  const [selectedFilesList, setSelectedFilesList] = useState<File[]>([]);
  const [uploadStates, setUploadStates] = useState<FileUploadState[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selectedFiles = watch("files");
  const fileCount = selectedFiles?.length || selectedFilesList.length;

  // Calculate overall progress
  // Calculate overall progress only for uploadable files (exclude files that already exist)
  const uploadableStates = uploadStates.filter(
    (s) => s.error !== "File already exists on server",
  );
  const overallProgress =
    uploadableStates.length > 0
      ? uploadableStates.reduce((sum, state) => sum + state.progress, 0) /
        uploadableStates.length
      : 0;
  
  // Count only files that will be uploaded (exclude files that already exist)
  const uploadableFilesCount = uploadStates.filter(
    (s) => s.status !== "failed" || s.error !== "File already exists on server",
  ).length;
  const uploadableCompleted = uploadStates.filter(
    (s) => s.status === "completed",
  ).length;
  const uploadableFailed = uploadStates.filter(
    (s) => s.status === "failed" && s.error !== "File already exists on server",
  ).length;

  /**
   * Check if files already exist on the backend
   * Returns array of files with their existence status
   */
  const checkFilesExistence = async (
    files: File[],
  ): Promise<Array<{ file: File; exists: boolean }>> => {
    const checks = await Promise.all(
      files.map(async (file) => {
        try {
          const result = await checkVideoExists({
            filename: file.name,
          }).unwrap();
          return { file, exists: result.exists };
        } catch (error) {
          // If check fails, assume file doesn't exist
          console.error(`Error checking file ${file.name}:`, error);
          return { file, exists: false };
        }
      }),
    );
    return checks;
  };

  /**
   * Upload a single file with progress tracking
   *
   * API IMPLEMENTATION HINTS:
   *
   * Backend endpoint: POST /api/v1/videos (configured in apiSlice baseUrl + endpoint)
   *
   * The endpoint should:
   * 1. Accept multipart/form-data with field name "file"
   * 2. Support chunked transfer encoding for progress tracking
   * 3. Return appropriate HTTP status codes (201 for success, 4xx/5xx for errors)
   * 4. Return Video object with metadata after processing
   *
   * Example backend (Express.js + Multer):
   * ```javascript
   * const multer = require('multer');
   * const upload = multer({ dest: 'uploads/videos/' });
   *
   * app.post('/api/v1/videos', upload.single('file'), (req, res) => {
   *   // req.file contains the uploaded file
   *   // Validate file type, size, etc.
   *   // Process the video (extract metadata, generate thumbnails, etc.)
   *   res.status(201).json({
   *     filename: req.file.originalname,
   *     width: 1920,
   *     height: 1080,
   *     fps: 30,
   *     frame_count: 300,
   *     codec: 'h264',
   *     duration: 10.0
   *   });
   * });
   * ```
   *
   * Example backend (FastAPI):
   * ```python
   * from fastapi import FastAPI, File, UploadFile
   *
   * @app.post("/api/v1/videos")
   * async def upload_video(file: UploadFile = File(...)):
   *     # Save file
   *     file_path = f"uploads/videos/{file.filename}"
   *     with open(file_path, "wb") as f:
   *         content = await file.read()
   *         f.write(content)
   *     # Extract video metadata using ffprobe or similar
   *     return {
   *         "filename": file.filename,
   *         "width": 1920,
   *         "height": 1080,
   *         "fps": 30.0,
   *         "frame_count": 300,
   *         "codec": "h264",
   *         "duration": 10.0
   *     }
   * ```
   */
  const uploadFile = async (
    file: File,
    onProgress: (progress: number) => void,
  ): Promise<void> => {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append("file", file); // Backend expects "file" field

      // Use XMLHttpRequest for progress tracking
      // Note: fetch() doesn't support upload progress natively
      const xhr = new XMLHttpRequest();

      // Track upload progress
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const progress = (e.loaded / e.total) * 100;
          onProgress(progress);
        }
      });

      // Handle completion
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      });

      // Handle errors
      xhr.addEventListener("error", () => {
        reject(new Error("Network error during upload"));
      });

      xhr.addEventListener("abort", () => {
        reject(new Error("Upload aborted"));
      });

      // Configure and send request to the correct API endpoint
      xhr.open("POST", "/api/v1/videos");
      xhr.send(formData);
    });
  };

  /**
   * Process uploads with concurrency limit
   * Uses a queue system to ensure max 3 concurrent uploads
   */
  const processUploadsWithConcurrency = async (
    files: FileUploadState[],
  ): Promise<{ succeeded: number; failed: number }> => {
    const queue = files.map((fileState, index) => ({ fileState, index }));
    const executing = new Set<Promise<void>>();
    let succeeded = 0;
    let failed = 0;

    for (const { fileState, index } of queue) {
      const uploadPromise = async () => {
        try {
          // Update status to uploading
          setUploadStates((prev) => {
            const newStates = [...prev];
            if (newStates[index]) {
              newStates[index] = { ...newStates[index], status: "uploading" };
            }
            return newStates;
          });

          // Upload with progress tracking
          await uploadFile(fileState.file, (progress) => {
            setUploadStates((prev) => {
              const newStates = [...prev];
              if (newStates[index]) {
                newStates[index] = { ...newStates[index], progress };
              }
              return newStates;
            });
          });

          // Mark as completed
          setUploadStates((prev) => {
            const newStates = [...prev];
            if (newStates[index]) {
              newStates[index] = {
                ...newStates[index],
                status: "completed",
                progress: 100,
              };
            }
            return newStates;
          });
          succeeded++;
        } catch (error) {
          // Mark as failed
          setUploadStates((prev) => {
            const newStates = [...prev];
            if (newStates[index]) {
              newStates[index] = {
                ...newStates[index],
                status: "failed",
                error: error instanceof Error ? error.message : "Upload failed",
              };
            }
            return newStates;
          });
          failed++;
        }
      };

      const promise = uploadPromise().finally(() => {
        executing.delete(promise);
      });

      executing.add(promise);

      // Limit concurrency - wait if we have MAX_CONCURRENT_UPLOADS running
      if (executing.size >= MAX_CONCURRENT_UPLOADS) {
        await Promise.race(executing);
      }
    }

    // Wait for remaining uploads
    await Promise.all(executing);

    return { succeeded, failed };
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFiles = Array.from(e.dataTransfer.files).filter((file) =>
      file.type.startsWith("video/"),
    );

    if (droppedFiles.length > 0) {
      // Filter out duplicates by filename (files already in the list)
      const existingFileNames = new Set(selectedFilesList.map((f) => f.name));
      const newFiles = droppedFiles.filter(
        (file) => !existingFileNames.has(file.name),
      );

      if (newFiles.length === 0) return;

      // Check which files already exist on backend
      const fileChecks = await checkFilesExistence(newFiles);

      // Add all new files to the list
      const allFiles = [...selectedFilesList, ...newFiles];
      setSelectedFilesList(allFiles);

      // Create a new FileList-like object for react-hook-form
      const dataTransfer = new DataTransfer();
      allFiles.forEach((file) => dataTransfer.items.add(file));
      setValue("files", dataTransfer.files);

      // Initialize upload states for new files
      const newUploadStates: FileUploadState[] = fileChecks.map(
        ({ file, exists }) => ({
          file,
          status: exists ? "failed" : "pending",
          progress: 0,
          error: exists ? "File already exists on server" : undefined,
        }),
      );

      setUploadStates((prev) => [...prev, ...newUploadStates]);
    }
  };

  const handleFileInputChange = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      // Filter out duplicates by filename (files already in the list)
      const existingFileNames = new Set(selectedFilesList.map((f) => f.name));
      const newFiles = Array.from(files).filter(
        (file) => !existingFileNames.has(file.name),
      );

      if (newFiles.length === 0) return;

      // Check which files already exist on backend
      const fileChecks = await checkFilesExistence(newFiles);

      // Add all new files to the list
      const allFiles = [...selectedFilesList, ...newFiles];
      setSelectedFilesList(allFiles);

      // Create a new FileList-like object for react-hook-form
      const dataTransfer = new DataTransfer();
      allFiles.forEach((file) => dataTransfer.items.add(file));
      setValue("files", dataTransfer.files);

      // Initialize upload states for new files
      const newUploadStates: FileUploadState[] = fileChecks.map(
        ({ file, exists }) => ({
          file,
          status: exists ? "failed" : "pending",
          progress: 0,
          error: exists ? "File already exists on server" : undefined,
        }),
      );

      setUploadStates((prev) => [...prev, ...newUploadStates]);
    }
  };

  const removeFile = (index: number) => {
    const newFiles = selectedFilesList.filter((_, i) => i !== index);
    const newUploadStates = uploadStates.filter((_, i) => i !== index);
    setSelectedFilesList(newFiles);
    setUploadStates(newUploadStates);

    if (newFiles.length === 0) {
      setValue("files", null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } else {
      const dataTransfer = new DataTransfer();
      newFiles.forEach((file) => dataTransfer.items.add(file));
      setValue("files", dataTransfer.files);
    }
  };

  const onSubmit = async () => {
    if (selectedFilesList.length === 0 || isUploading) {
      return;
    }

    setIsUploading(true);

    // Filter out files that already failed (exist on server)
    // and only initialize upload states for files that need to be uploaded
    const filesToUpload: FileUploadState[] = uploadStates
      .filter((state) => state.status === "pending")
      .map((state) => ({ ...state }));

    // If there are no files to upload (all failed checks), just stop
    if (filesToUpload.length === 0) {
      setIsUploading(false);
      return;
    }

    try {
      // Process uploads with concurrency control
      const { succeeded, failed } =
        await processUploadsWithConcurrency(filesToUpload);

      // Check if all uploadable files succeeded
      if (failed === 0 && succeeded === filesToUpload.length) {
        // Invalidate videos cache to refetch the updated list
        dispatch(api.util.invalidateTags(["videos"]));

        // Reset form after successful upload
        setTimeout(() => {
          setSelectedFilesList([]);
          setUploadStates([]);
          reset();
          if (fileInputRef.current) {
            fileInputRef.current.value = "";
          }
          setIsUploading(false);
        }, 2000); // Show success state for 2 seconds
      } else {
        setIsUploading(false);
      }
    } catch (error) {
      console.error("Upload error:", error);
      setIsUploading(false);
    }
  };
  const filteredVideos =
    isSuccess && videos ? filterOutTransportStreams(videos) : [];

  if (isSuccess && filteredVideos.length > 0) {
    return (
      <div className="container pl-16 mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Videos</h1>
          <p className="text-muted-foreground mt-2">
            Ready-to-use video clips available in the platform
          </p>
        </div>

        {/* Multi-file Upload Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="mb-8">
          <div className="border p-6 bg-card">
            <h2 className="text-xl font-semibold mb-4">Upload Videos</h2>
            <div className="space-y-4">
              {/* Drag and Drop Zone */}
              <div
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`
                  relative border-2 border-dashed p-8
                  transition-all duration-200 cursor-pointer
                  flex flex-col items-center justify-center gap-3
                  ${
                    isDragging
                      ? "border-primary bg-primary/5 scale-[1.02]"
                      : "border-muted-foreground/25 hover:border-primary/50 hover:bg-accent/50"
                  }
                `}
              >
                <Upload
                  className={`w-12 h-12 ${
                    isDragging ? "text-primary" : "text-muted-foreground"
                  }`}
                />
                <div className="text-center">
                  <p className="text-lg font-medium">
                    {isDragging
                      ? "Drop your video files here"
                      : "Drag & drop video files here"}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    or click to browse your computer
                  </p>
                </div>
                <Input
                  {...register("files", {
                    onChange: handleFileInputChange,
                  })}
                  ref={(e) => {
                    register("files").ref(e);
                    fileInputRef.current = e;
                  }}
                  id="video-files"
                  type="file"
                  accept="video/*"
                  multiple
                  className="hidden"
                />
              </div>

              {/* Selected Files List */}
              {selectedFilesList.length > 0 && (
                <div className="space-y-2">
                  <Label className="text-sm font-medium">
                    Selected files ({selectedFilesList.length})
                  </Label>

                  {/* Overall Progress */}
                  {isUploading && (
                    <div className="space-y-2 p-4 border bg-muted/50">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">Overall Progress</span>
                        <span className="text-muted-foreground">
                          {uploadableCompleted}/{uploadableFilesCount} completed
                          {uploadableFailed > 0 &&
                            ` • ${uploadableFailed} failed`}
                        </span>
                      </div>
                      <Progress value={overallProgress} className="h-2" />
                      <div className="text-xs text-muted-foreground">
                        {Math.round(overallProgress)}% complete • Max{" "}
                        {MAX_CONCURRENT_UPLOADS} concurrent uploads
                        {uploadStates.length - uploadableFilesCount > 0 &&
                          ` • ${uploadStates.length - uploadableFilesCount} skipped (already exists)`}
                      </div>
                    </div>
                  )}

                  <div className="border divide-y max-h-60 overflow-y-auto">
                    {selectedFilesList.map((file, index) => {
                      const uploadState = uploadStates[index];
                      const status = uploadState?.status ?? "pending";
                      const progress = uploadState?.progress ?? 0;

                      return (
                        <div
                          key={`${file.name}-${index}`}
                          className="p-3 hover:bg-accent/50 transition-colors"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex-1 min-w-0 flex items-center gap-2">
                              {status === "uploading" && (
                                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                              )}
                              {status === "completed" && (
                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                              )}
                              {status === "failed" && (
                                <AlertCircle className="h-4 w-4 text-destructive" />
                              )}
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium truncate">
                                  {file.name}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {(file.size / (1024 * 1024)).toFixed(2)} MB
                                  {status === "failed" &&
                                    uploadState?.error &&
                                    ` • ${uploadState.error}`}
                                </p>
                              </div>
                            </div>
                            {!isUploading && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => removeFile(index)}
                                className="ml-2 h-8 w-8 p-0"
                              >
                                <X className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                          {(status === "uploading" ||
                            status === "completed") && (
                            <Progress value={progress} className="h-1" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                {fileCount > 0 && (
                  <Button
                    type="submit"
                    disabled={isUploading || uploadableFilesCount === 0}
                  >
                    {isUploading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Uploading...
                      </>
                    ) : (
                      <>
                        Upload{" "}
                        {uploadableFilesCount > 0 &&
                          `${uploadableFilesCount} file${uploadableFilesCount !== 1 ? "s" : ""}`}
                      </>
                    )}
                  </Button>
                )}
                {uploadableFailed > 0 && !isUploading && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      // Retry only files that failed for reasons other than "already exists"
                      // Reset their status to pending
                      setUploadStates((prev) =>
                        prev.map((state) =>
                          state.status === "failed" &&
                          state.error !== "File already exists on server"
                            ? {
                                ...state,
                                status: "pending",
                                progress: 0,
                                error: undefined,
                              }
                            : state,
                        ),
                      );

                      // Trigger upload
                      handleSubmit(onSubmit)();
                    }}
                  >
                    Retry {uploadableFailed} failed
                  </Button>
                )}
                {fileCount > 0 && !isUploading && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setSelectedFilesList([]);
                      setUploadStates([]);
                      reset();
                      if (fileInputRef.current) {
                        fileInputRef.current.value = "";
                      }
                    }}
                  >
                    Clear all
                  </Button>
                )}
              </div>
            </div>
          </div>
        </form>

        <Table>
          <TableCaption>A list of loaded videos.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[25%]">File name</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Number of frames</TableHead>
              <TableHead>Codec</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredVideos.map((video) => (
              <TableRow key={video.filename}>
                <TableCell className="font-medium">{video.filename}</TableCell>
                <TableCell>
                  {video.width}x{video.height}
                </TableCell>
                <TableCell>{video.frame_count}</TableCell>
                <TableCell>{video.codec}</TableCell>
                <TableCell>
                  {formatElapsedTimeSeconds(video.duration)}
                </TableCell>
                <TableCell>
                  <video
                    src={`/assets/videos/input/${video.filename}`}
                    controls
                    className="w-48 h-auto"
                  >
                    Your browser does not support the video tag.
                  </video>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading videos</div>
    </div>
  );
};
