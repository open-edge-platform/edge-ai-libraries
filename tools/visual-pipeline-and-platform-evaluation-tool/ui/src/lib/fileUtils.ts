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
