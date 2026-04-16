import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Label } from "@/components/ui/label.tsx";
import { Progress } from "@/components/ui/progress.tsx";
import React, { useRef, useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Upload,
  X,
} from "lucide-react";

type UploadFormData = {
  files: FileList | null;
};

type FileUploadState = {
  file: File;
  status: "pending" | "uploading" | "completed" | "failed";
  progress: number;
  error?: string;
};

type FileUploadJob = FileUploadState & {
  originalIndex: number;
};

export interface MultiFileUploaderProps {
  accept: string;
  uploadEndpoint: string;
  checkFileExists: (filename: string) => Promise<{ exists: boolean }>;
  onUploadComplete?: (succeeded: number, failed: number) => void;
  onUploadProgress?: (
    jobs: Array<{ id: string; name: string; progress: number }>,
  ) => void;
  multiple?: boolean;
  maxConcurrentUploads?: number;
  className?: string;
}

export const MultiFileUploader = ({
  accept,
  uploadEndpoint,
  checkFileExists,
  onUploadComplete,
  onUploadProgress,
  multiple = true,
  maxConcurrentUploads = 3,
  className,
}: MultiFileUploaderProps) => {
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
  const [isPostUpload, setIsPostUpload] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selectedFiles = watch("files");
  const fileCount = selectedFiles?.length || selectedFilesList.length;

  const uploadableStates = uploadStates.filter(
    (s) => s.error !== "File already exists on server",
  );
  const overallProgress =
    uploadableStates.length > 0
      ? uploadableStates.reduce((sum, state) => sum + state.progress, 0) /
        uploadableStates.length
      : 0;

  const uploadableFilesCount = uploadStates.filter(
    (s) => s.error !== "File already exists on server",
  ).length;
  const uploadableCompleted = uploadStates.filter(
    (s) => s.status === "completed",
  ).length;
  const uploadableFailed = uploadStates.filter(
    (s) => s.status === "failed" && s.error !== "File already exists on server",
  ).length;

  useEffect(() => {
    if (onUploadProgress) {
      const jobs = uploadStates
        .filter((state) => state.error !== "File already exists on server")
        .map((state, index) => ({
          id: `file-${index}-${state.file.name}`,
          name: state.file.name,
          progress: state.progress,
        }));

      onUploadProgress(jobs);
    }
  }, [uploadStates, onUploadProgress]);

  const checkFilesExistence = async (
    files: File[],
  ): Promise<Array<{ file: File; exists: boolean }>> =>
    await Promise.all(
      files.map(async (file) => {
        try {
          const result = await checkFileExists(file.name);
          return { file, exists: result.exists };
        } catch (error) {
          console.error(`Error checking file ${file.name}:`, error);
          return { file, exists: false };
        }
      }),
    );

  const uploadFile = async (
    file: File,
    onProgress: (progress: number) => void,
  ): Promise<void> => {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append("file", file);

      // Use XMLHttpRequest for progress tracking
      // Note: RTKQuery or fetch() doesn't support upload progress natively
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const progress = (e.loaded / e.total) * 100;
          onProgress(progress);
        }
      });

      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve();
        } else {
          try {
            const response = JSON.parse(xhr.responseText);
            const detail =
              response.detail || `Upload failed with status ${xhr.status}`;
            reject(new Error(detail));
          } catch {
            reject(new Error(`Upload failed with status ${xhr.status}`));
          }
        }
      });

      xhr.addEventListener("error", () => {
        reject(new Error("Network error during upload"));
      });

      xhr.addEventListener("abort", () => {
        reject(new Error("Upload aborted"));
      });

      xhr.open("POST", uploadEndpoint);
      xhr.send(formData);
    });
  };

  const processParallelUploads = async (
    files: FileUploadJob[],
  ): Promise<{ succeeded: number; failed: number }> => {
    const executing = new Set<Promise<void>>();
    let succeeded = 0;
    let failed = 0;

    for (const fileJob of files) {
      const uploadPromise = async () => {
        const { originalIndex } = fileJob;
        try {
          setUploadStates((prev) => {
            const newStates = [...prev];
            if (newStates[originalIndex]) {
              newStates[originalIndex] = {
                ...newStates[originalIndex],
                status: "uploading",
              };
            }
            return newStates;
          });

          await uploadFile(fileJob.file, (progress) => {
            setUploadStates((prev) => {
              const newStates = [...prev];
              if (newStates[originalIndex]) {
                newStates[originalIndex] = {
                  ...newStates[originalIndex],
                  progress,
                };
              }
              return newStates;
            });
          });

          setUploadStates((prev) => {
            const newStates = [...prev];
            if (newStates[originalIndex]) {
              newStates[originalIndex] = {
                ...newStates[originalIndex],
                status: "completed",
                progress: 100,
              };
            }
            return newStates;
          });
          succeeded++;
        } catch (error) {
          setUploadStates((prev) => {
            const newStates = [...prev];
            if (newStates[originalIndex]) {
              newStates[originalIndex] = {
                ...newStates[originalIndex],
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

      if (executing.size >= maxConcurrentUploads) {
        await Promise.race(executing);
      }
    }

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

  const filterFilesByAccept = (files: File[]): File[] => {
    if (accept === "*" || accept === "*/*") {
      return files;
    }

    if (accept.includes("/*")) {
      const typePrefix = accept.split("/")[0];
      return files.filter((file) => file.type.startsWith(`${typePrefix}/`));
    }

    if (accept.startsWith(".")) {
      const extensions = accept
        .split(",")
        .map((ext) => ext.trim().toLowerCase());
      return files.filter((file) => {
        const fileExt = `.${file.name.split(".").pop()?.toLowerCase()}`;
        return extensions.includes(fileExt);
      });
    }

    const acceptedTypes = accept.split(",").map((type) => type.trim());
    return files.filter((file) => acceptedTypes.includes(file.type));
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFiles = filterFilesByAccept(Array.from(e.dataTransfer.files));

    if (droppedFiles.length > 0) {
      await addFiles(droppedFiles);
    }
  };

  const handleFileInputChange = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await addFiles(Array.from(files));
    }
  };

  const addFiles = async (newFilesToAdd: File[]) => {
    const shouldReplaceList = isPostUpload;

    const baseFiles = shouldReplaceList ? [] : selectedFilesList;

    const existingFileNames = new Set(baseFiles.map((f) => f.name));
    const newFiles = newFilesToAdd.filter(
      (file) => !existingFileNames.has(file.name),
    );

    if (newFiles.length === 0) return;

    const fileChecks = await checkFilesExistence(newFiles);

    const allFiles = [...baseFiles, ...newFiles];
    setSelectedFilesList(allFiles);

    if (shouldReplaceList) {
      setIsPostUpload(false);
    }

    // Create FileList-like object for react-hook-form
    const dataTransfer = new DataTransfer();
    allFiles.forEach((file) => dataTransfer.items.add(file));
    setValue("files", dataTransfer.files);

    const newUploadStates: FileUploadState[] = fileChecks.map(
      ({ file, exists }) => ({
        file,
        status: exists ? "failed" : "pending",
        progress: 0,
        error: exists ? "File already exists on server" : undefined,
      }),
    );

    setUploadStates(
      shouldReplaceList
        ? newUploadStates
        : [...uploadStates, ...newUploadStates],
    );
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

    const filesToUpload: FileUploadJob[] = uploadStates
      .map((state, originalIndex) => ({ ...state, originalIndex }))
      .filter((state) => state.status === "pending");

    if (filesToUpload.length === 0) {
      setIsUploading(false);
      return;
    }

    try {
      const { succeeded, failed } = await processParallelUploads(filesToUpload);

      if (onUploadComplete) {
        onUploadComplete(succeeded, failed);
      }

      if (failed === 0 && succeeded === filesToUpload.length) {
        setTimeout(() => {
          setSelectedFilesList([]);
          setUploadStates([]);
          reset();
          if (fileInputRef.current) {
            fileInputRef.current.value = "";
          }
          setIsUploading(false);
          setIsPostUpload(true);
        }, 2000);
      } else {
        setIsUploading(false);
        setIsPostUpload(true);
      }
    } catch (error) {
      console.error("Upload error:", error);
      setIsUploading(false);
      setIsPostUpload(true);
    }
  };

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className={className}
      aria-label="File upload form"
    >
      <div className="border p-6 bg-card">
        <h2 id="upload-heading" className="text-xl font-semibold mb-4">
          Upload Files
        </h2>
        <div className="space-y-4">
          <div
            role="button"
            tabIndex={0}
            aria-label={`Drop zone for files. Click or press Enter to browse. Accepts ${accept} files.`}
            aria-describedby="upload-instructions"
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            className={`
              relative border-2 border-dashed p-8 bg-background
              transition-all duration-200 cursor-pointer
              flex flex-col items-center justify-center gap-3
              focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2
              ${
                isDragging
                  ? "border-primary bg-primary/5 scale-[1.02]"
                  : "border-muted-foreground/25 hover:border-primary/50 hover:bg-background/50"
              }
            `}
          >
            <Upload
              className={`w-12 h-12 ${
                isDragging ? "text-primary" : "text-muted-foreground"
              }`}
              aria-hidden="true"
            />
            <div className="text-center">
              <p id="upload-instructions" className="text-lg font-medium">
                {isDragging ? "Drop your files here" : "Drag & drop files here"}
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
              id="file-upload-input"
              type="file"
              accept={accept}
              multiple={multiple}
              className="hidden"
              aria-hidden="true"
              tabIndex={-1}
            />
          </div>

          {selectedFilesList.length > 0 && (
            <div
              className="space-y-2"
              role="region"
              aria-label="Selected files"
            >
              <Label className="text-sm font-medium" id="files-list-label">
                Selected files ({selectedFilesList.length})
              </Label>

              {isUploading && (
                <div
                  className="space-y-2 p-4 border bg-background"
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                >
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">Overall Progress</span>
                    <span className="text-muted-foreground">
                      {uploadableCompleted}/{uploadableFilesCount} completed
                      {uploadableFailed > 0 && ` • ${uploadableFailed} failed`}
                    </span>
                  </div>
                  <Progress
                    value={overallProgress}
                    className="h-2"
                    aria-label={`Overall upload progress: ${Math.round(overallProgress)}%`}
                  />
                  <div className="text-xs text-muted-foreground">
                    {Math.round(overallProgress)}% complete
                    {uploadStates.length - uploadableFilesCount > 0 &&
                      ` • ${uploadStates.length - uploadableFilesCount} skipped (already exists)`}
                  </div>
                </div>
              )}

              <div
                className="border divide-y max-h-60 overflow-y-auto"
                role="list"
                aria-labelledby="files-list-label"
              >
                {selectedFilesList.map((file, index) => {
                  const uploadState = uploadStates[index];
                  const status = uploadState?.status ?? "pending";
                  const progress = uploadState?.progress ?? 0;
                  const isExistingFile =
                    uploadState?.error === "File already exists on server";
                  const statusText = isExistingFile
                    ? "already exists"
                    : status === "uploading"
                      ? "uploading"
                      : status === "completed"
                        ? "completed"
                        : status === "failed"
                          ? "failed"
                          : "pending";

                  return (
                    <div
                      key={`${file.name}-${index}`}
                      className="px-3 py-2 bg-background hover:bg-background/50 transition-colors"
                      role="listitem"
                      aria-label={`${file.name}, ${(file.size / (1024 * 1024)).toFixed(2)} MB, status: ${statusText}`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex-1 min-w-0 flex items-center gap-2">
                          {status === "uploading" && (
                            <Loader2
                              className="h-4 w-4 animate-spin text-primary"
                              aria-hidden="true"
                            />
                          )}
                          {status === "completed" && (
                            <CheckCircle2
                              className="h-4 w-4 text-status-success"
                              aria-label="Upload successful"
                            />
                          )}
                          {status === "failed" && isExistingFile && (
                            <AlertTriangle
                              className="h-4 w-4"
                              aria-label="File already exists"
                            />
                          )}
                          {status === "failed" && !isExistingFile && (
                            <AlertCircle
                              className="h-4 w-4 text-destructive"
                              aria-label="Upload failed"
                            />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">
                              {file.name}
                            </p>
                            <p
                              className={`text-xs ${
                                status === "failed" && !isExistingFile
                                  ? "text-destructive"
                                  : "text-muted-foreground"
                              }`}
                            >
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
                            aria-label={`Remove ${file.name} from upload list`}
                          >
                            <X className="h-4 w-4" aria-hidden="true" />
                          </Button>
                        )}
                      </div>
                      {(status === "uploading" || status === "completed") && (
                        <Progress
                          value={progress}
                          className="h-1"
                          aria-label={`Upload progress for ${file.name}: ${Math.round(progress)}%`}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex gap-2" role="group" aria-label="Upload actions">
            {fileCount > 0 &&
              !isUploading &&
              uploadStates.some((s) => s.status === "pending") && (
                <Button
                  type="submit"
                  disabled={uploadableFilesCount === 0}
                  aria-label={`Upload ${uploadableFilesCount} file${uploadableFilesCount !== 1 ? "s" : ""}`}
                >
                  Upload{" "}
                  {uploadableFilesCount > 0 &&
                    `${uploadableFilesCount} file${uploadableFilesCount !== 1 ? "s" : ""}`}
                </Button>
              )}
            {fileCount > 0 && isUploading && (
              <Button type="button" disabled aria-label="Upload in progress">
                <Loader2
                  className="mr-2 h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
                Uploading...
              </Button>
            )}
            {fileCount > 0 && !isUploading && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setSelectedFilesList([]);
                  setUploadStates([]);
                  setIsPostUpload(false);
                  reset();
                  if (fileInputRef.current) {
                    fileInputRef.current.value = "";
                  }
                }}
                aria-label="Clear all selected files"
              >
                Clear all
              </Button>
            )}
          </div>
        </div>
      </div>
    </form>
  );
};
