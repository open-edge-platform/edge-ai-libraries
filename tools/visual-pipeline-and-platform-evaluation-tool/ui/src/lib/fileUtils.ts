/**
 * Common MIME types for file downloads
 */
export const MimeType = {
  TEXT: "text/plain",
  JSON: "application/json",
  HTML: "text/html",
  CSV: "text/csv",
  XML: "application/xml",
  PDF: "application/pdf",
} as const;

/**
 * Downloads a Blob to the user's system
 * @param blob - The Blob object to download
 * @param filename - The name of the file to save
 * @private
 */
const downloadBlob = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

/**
 * Downloads a file to the user's system
 * @param content - The content to download
 * @param filename - The name of the file to download
 * @param mimeType - The MIME type of the file (default: "text/plain")
 */
export const downloadFile = (
  content: string,
  filename: string,
  mimeType: string = MimeType.TEXT,
) => {
  const blob = new Blob([content], { type: mimeType });
  downloadBlob(blob, filename);
};

/**
 * Extracts the filename from a file path
 * @param value - The file path (can be Unix or Windows format)
 * @returns The filename extracted from the path
 */
export const getFilenameFromPath = (value: unknown): string => {
  return (
    String(value ?? "")
      .split(/[\\/]/)
      .pop() ?? ""
  );
};

/**
 * Formats a byte size into a human-readable string
 * @param bytes - The size in bytes
 * @returns A formatted string with the appropriate unit (B, KB, MB, GB)
 */
export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
};

/**
 * Downloads a Response object as a file to the user's system
 * Extracts the filename from the Content-Disposition header if available
 * @param response - The Response object containing the file data
 * @param fallbackFilename - The filename to use if none is provided in the response headers
 */
export const downloadResponseAsFile = async (
  response: Response,
  fallbackFilename: string,
): Promise<void> => {
  const filename = getFilenameFromContentDisposition(
    response.headers.get("content-disposition"),
    fallbackFilename,
  );

  const blob = await response.blob();
  downloadBlob(blob, filename);
};

const getFilenameFromContentDisposition = (
  contentDisposition: string | null,
  fallbackFilename: string,
): string => {
  if (!contentDisposition) return fallbackFilename;

  const filenameMatch = contentDisposition.match(
    /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i,
  );

  const rawFilename = filenameMatch?.[1] ?? filenameMatch?.[2] ?? "";
  if (!rawFilename) return fallbackFilename;

  try {
    return decodeURIComponent(rawFilename);
  } catch {
    return rawFilename;
  }
};
