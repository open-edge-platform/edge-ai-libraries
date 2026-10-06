const EPSILON_MM = 0.01;

/**
 * Computes the mm offsets, within a captured image, where each PDF page
 * should start (`boundaries[i]`) and end (`boundaries[i + 1]`), such that:
 *  - no page exceeds `visibleHeightPerPage` mm of content, and
 *  - breaks snap to the furthest available row boundary that still fits,
 *    instead of an arbitrary offset that could cut a table row in half.
 *
 * If a single row is taller than a full page (or no row boundaries are
 * available, e.g. non-tabular content), the break falls back to a hard
 * cut at exactly `visibleHeightPerPage`.
 *
 * This is a pure function (no DOM/canvas access) so it can be unit tested
 * in isolation from the rest of the export pipeline.
 *
 * @param imageHeightMm Total height of the captured image, in mm.
 * @param visibleHeightPerPage Usable page height (page height minus
 *   top/bottom padding), in mm.
 * @param rowBreakOffsetsMm Bottom edges of table rows, in mm, relative to
 *   the top of the captured image. Does not need to be pre-sorted.
 * @returns Sorted mm offsets `[0, ...breaks, imageHeightMm]`. Page `i`
 *   spans `boundaries[i]` to `boundaries[i + 1]`.
 */
export const computePageBoundariesMm = (
  imageHeightMm: number,
  visibleHeightPerPage: number,
  rowBreakOffsetsMm: number[],
): number[] => {
  if (imageHeightMm <= 0) {
    return [0, 0];
  }

  if (visibleHeightPerPage <= 0) {
    throw new Error(
      "PDF page padding leaves no visible height per page; reduce pagePaddingMm.",
    );
  }

  const sortedRowBreaksMm = [...rowBreakOffsetsMm].sort((a, b) => a - b);
  const pageStartOffsetsMm = [0];
  let cursor = 0;

  while (cursor + visibleHeightPerPage < imageHeightMm - EPSILON_MM) {
    const maxReach = cursor + visibleHeightPerPage;
    const candidates = sortedRowBreaksMm.filter(
      (offset) =>
        offset > cursor + EPSILON_MM && offset <= maxReach + EPSILON_MM,
    );
    const nextBreak =
      candidates.length > 0 ? candidates[candidates.length - 1] : maxReach;

    cursor = nextBreak > cursor ? nextBreak : maxReach;
    pageStartOffsetsMm.push(cursor);
  }

  return [...pageStartOffsetsMm, imageHeightMm];
};
