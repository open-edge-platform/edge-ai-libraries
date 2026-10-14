import { format } from "date-fns";
import jsPDF from "jspdf";
import {
  captureNodeAsImage,
  isPdfExportIgnored,
} from "@/lib/pdf/pdfDomCapture";
import {
  fillPdfPageBackground,
  getPdfBackground,
} from "@/lib/pdf/pdfBackground";
import { createImageSlicer, loadImage } from "@/lib/pdf/pdfImage";
import { computePageBoundariesMm } from "@/lib/pdf/pdfPagination";

export type { PdfBackgroundRgb } from "@/lib/pdf/pdfBackground";
export {
  fillPdfPageBackground,
  getPdfBackground,
} from "@/lib/pdf/pdfBackground";
export { isPdfExportIgnored } from "@/lib/pdf/pdfDomCapture";
export { loadImage } from "@/lib/pdf/pdfImage";

type ExportNodeToPdfOptions = {
  filename: string;
  node: HTMLElement;
  isDarkMode?: boolean;
  filter?: (node: Node) => boolean;
  pagePaddingMm?: number;
  imageQuality?: number;
};

const DEFAULT_PAGE_PADDING_MM = 10;
const DEFAULT_IMAGE_QUALITY = 0.95;

export const formatFilenameTimestamp = (timestamp: number) =>
  format(new Date(timestamp), "yyyy-MM-dd-HH-mm-ss");

export const exportNodeToPdf = async ({
  filename,
  node,
  isDarkMode = false,
  filter,
  pagePaddingMm = DEFAULT_PAGE_PADDING_MM,
  imageQuality = DEFAULT_IMAGE_QUALITY,
}: ExportNodeToPdfOptions) => {
  const { backgroundColor, backgroundRgb } = getPdfBackground(isDarkMode);
  const exportFilter = (nodeToFilter: Node) =>
    isPdfExportIgnored(nodeToFilter) ? false : (filter?.(nodeToFilter) ?? true);

  const {
    imageData,
    format: imageFormat,
    rowBreakOffsetsPx,
  } = await captureNodeAsImage({
    node,
    backgroundColor,
    imageQuality,
    filter: exportFilter,
  });

  const img = await loadImage(imageData);
  const pdf = new jsPDF("p", "mm", "a4");
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const imgWidth = pageWidth - pagePaddingMm * 2;
  const imgHeight = (img.height * imgWidth) / img.width;
  const visibleHeightPerPage = pageHeight - pagePaddingMm * 2;

  const scale = imgWidth / img.width;
  const rowBreaksMm = rowBreakOffsetsPx.map((offsetPx) => offsetPx * scale);

  const pageBoundariesMm = computePageBoundariesMm(
    imgHeight,
    visibleHeightPerPage,
    rowBreaksMm,
  );
  const pageCount = pageBoundariesMm.length - 1;
  const sliceImage = createImageSlicer(img);
  const pdfImageFormat = imageFormat === "image/jpeg" ? "JPEG" : "PNG";

  for (let index = 0; index < pageCount; index += 1) {
    const startMm = pageBoundariesMm[index];
    const endMm = pageBoundariesMm[index + 1];
    const sliceHeightMm = endMm - startMm;
    const sliceDataUrl = sliceImage(
      startMm / scale,
      sliceHeightMm / scale,
      imageFormat,
      imageQuality,
    );

    if (index > 0) {
      pdf.addPage();
    }

    fillPdfPageBackground(pdf, pageWidth, pageHeight, backgroundRgb);
    pdf.addImage(
      sliceDataUrl,
      pdfImageFormat,
      pagePaddingMm,
      pagePaddingMm,
      imgWidth,
      sliceHeightMm,
    );
  }

  pdf.save(filename);
};
