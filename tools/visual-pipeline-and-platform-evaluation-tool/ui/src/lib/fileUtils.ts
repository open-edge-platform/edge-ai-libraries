export const MimeType = {
  TEXT: "text/plain",
  JSON: "application/json",
  HTML: "text/html",
  CSV: "text/csv",
  XML: "application/xml",
  PDF: "application/pdf",
} as const;

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
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

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
