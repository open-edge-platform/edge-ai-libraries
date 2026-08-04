import { format } from "date-fns";
import domtoimage from "dom-to-image";
import jsPDF from "jspdf";

export type PdfBackgroundRgb = [number, number, number];

const PDF_EXPORT_IGNORE_ATTRIBUTE = "data-export-ignore";

type ExportNodeToPdfOptions = {
  filename: string;
  node: HTMLElement;
  isDarkMode?: boolean;
  filter?: (node: Node) => boolean;
  pagePaddingMm?: number;
  imageQuality?: number;
};

type PdfBackground = {
  backgroundColor: string;
  backgroundRgb: PdfBackgroundRgb;
};

const DEFAULT_PAGE_PADDING_MM = 10;
const DEFAULT_IMAGE_QUALITY = 0.95;
const LIGHT_PDF_BACKGROUND_HEX = "#ffffff";
const LIGHT_PDF_BACKGROUND_RGB: PdfBackgroundRgb = [255, 255, 255];
const DARK_PDF_BACKGROUND_HEX = "#242528";
const DARK_PDF_BACKGROUND_RGB: PdfBackgroundRgb = [36, 37, 40];

export const isPdfExportIgnored = (node: Node) =>
  node instanceof Element && node.hasAttribute(PDF_EXPORT_IGNORE_ATTRIBUTE);

export const formatFilenameTimestamp = (timestamp: number) =>
  format(new Date(timestamp), "yyyy-MM-dd-HH-mm-ss");

export const getPdfBackground = (isDarkMode: boolean): PdfBackground => {
  if (isDarkMode) {
    return {
      backgroundColor: DARK_PDF_BACKGROUND_HEX,
      backgroundRgb: DARK_PDF_BACKGROUND_RGB,
    };
  }

  return {
    backgroundColor: LIGHT_PDF_BACKGROUND_HEX,
    backgroundRgb: LIGHT_PDF_BACKGROUND_RGB,
  };
};

export const fillPdfPageBackground = (
  pdf: jsPDF,
  pageWidth: number,
  pageHeight: number,
  backgroundRgb: PdfBackgroundRgb,
) => {
  pdf.setFillColor(...backgroundRgb);
  pdf.rect(0, 0, pageWidth, pageHeight, "F");
};

export const loadImage = (src: string) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });

export const exportNodeToPdf = async ({
  filename,
  node,
  isDarkMode = false,
  filter,
  pagePaddingMm = DEFAULT_PAGE_PADDING_MM,
  imageQuality = DEFAULT_IMAGE_QUALITY,
}: ExportNodeToPdfOptions) => {
  const { backgroundColor, backgroundRgb } = getPdfBackground(isDarkMode);
  const exportFilter = (nodeToFilter: Node) => {
    if (isPdfExportIgnored(nodeToFilter)) {
      return false;
    }

    return filter ? filter(nodeToFilter) : true;
  };

  const imgData = await domtoimage.toPng(node, {
    bgcolor: backgroundColor,
    quality: imageQuality,
    filter: exportFilter,
  });

  const img = await loadImage(imgData);
  const pdf = new jsPDF("p", "mm", "a4");
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const imgWidth = pageWidth - pagePaddingMm * 2;
  const imgHeight = (img.height * imgWidth) / img.width;

  fillPdfPageBackground(pdf, pageWidth, pageHeight, backgroundRgb);
  pdf.addImage(
    imgData,
    "PNG",
    pagePaddingMm,
    pagePaddingMm,
    imgWidth,
    imgHeight,
  );

  const visibleHeightPerPage = pageHeight - pagePaddingMm * 2;
  let remainingHeight = imgHeight - visibleHeightPerPage;
  let currentPage = 1;

  while (remainingHeight > 0) {
    pdf.addPage();
    fillPdfPageBackground(pdf, pageWidth, pageHeight, backgroundRgb);
    const yOffset = pagePaddingMm - currentPage * visibleHeightPerPage;
    pdf.addImage(imgData, "PNG", pagePaddingMm, yOffset, imgWidth, imgHeight);
    remainingHeight -= visibleHeightPerPage;
    currentPage += 1;
  }

  pdf.save(filename);
};
