import type jsPDF from "jspdf";

export type PdfBackgroundRgb = [number, number, number];

export type PdfBackground = {
  backgroundColor: string;
  backgroundRgb: PdfBackgroundRgb;
};

const LIGHT_PDF_BACKGROUND_HEX = "#ffffff";
const LIGHT_PDF_BACKGROUND_RGB: PdfBackgroundRgb = [255, 255, 255];
const DARK_PDF_BACKGROUND_HEX = "#242528";
const DARK_PDF_BACKGROUND_RGB: PdfBackgroundRgb = [36, 37, 40];

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
