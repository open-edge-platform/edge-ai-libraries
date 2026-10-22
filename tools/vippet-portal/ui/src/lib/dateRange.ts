/** Inclusive from/to day filter shared by the result selection views. */

export type DateRange = {
  /** `yyyy-MM-dd`, or "" for an open bound. */
  from: string;
  to: string;
};

export const EMPTY_DATE_RANGE: DateRange = { from: "", to: "" };

export const isDateRangeActive = (range: DateRange) =>
  Boolean(range.from || range.to);

/** Bounds are interpreted in local time and both ends are inclusive. */
export const isWithinDateRange = (
  timestamp: number | null | undefined,
  range: DateRange,
) => {
  if (!isDateRangeActive(range)) return true;
  // An undated result cannot be proven to fall inside an active range.
  if (timestamp == null) return false;
  if (range.from && timestamp < new Date(`${range.from}T00:00:00`).getTime()) {
    return false;
  }
  if (range.to && timestamp > new Date(`${range.to}T23:59:59.999`).getTime()) {
    return false;
  }
  return true;
};
