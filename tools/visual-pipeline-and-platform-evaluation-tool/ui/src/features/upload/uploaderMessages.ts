export const PRE_UPLOAD_MESSAGES = {
  FILE_EXISTS: "File already exists on server",
  INVALID_ARCHIVE: "Failed to read archive. Ensure it is a valid zip file.",
  MISSING_REQUIRED_FILES:
    "Archive is missing required model files (model.bin, model.xml).",
} as const;

export type PreUploadMessage =
  (typeof PRE_UPLOAD_MESSAGES)[keyof typeof PRE_UPLOAD_MESSAGES];
