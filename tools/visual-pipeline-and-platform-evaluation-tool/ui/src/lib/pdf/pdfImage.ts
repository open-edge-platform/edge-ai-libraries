export const loadImage = (src: string) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });

export type ImageMimeType = "image/png" | "image/jpeg";

/**
 * Creates a reusable cropper for slicing horizontal bands out of a source
 * image. Placing the same full (uncropped) image at a shifted offset for
 * each PDF page relies on the page boundary clipping anything outside its
 * bounds, which leaves no real blank margin (the "margin" area ends up
 * showing leftover content from just before the break). Cropping each
 * page's slice into its own image up front avoids that entirely.
 *
 * A single backing canvas is reused across calls (just resized per slice)
 * to avoid allocating a new canvas per PDF page.
 */
export const createImageSlicer = (img: HTMLImageElement) => {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");

  if (!ctx) {
    throw new Error("Failed to acquire 2D canvas context for PDF export.");
  }

  canvas.width = img.width;

  return (
    sourceStartPx: number,
    sourceHeightPx: number,
    mimeType: ImageMimeType,
    quality?: number,
  ): string => {
    const clampedStartPx = Math.max(0, Math.round(sourceStartPx));
    const maxHeightPx = Math.max(0, img.height - clampedStartPx);
    const sliceHeightPx = Math.max(
      1,
      Math.min(Math.round(sourceHeightPx), maxHeightPx || 1),
    );

    canvas.height = sliceHeightPx;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(
      img,
      0,
      clampedStartPx,
      img.width,
      sliceHeightPx,
      0,
      0,
      img.width,
      sliceHeightPx,
    );

    return canvas.toDataURL(mimeType, quality);
  };
};
