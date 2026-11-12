/** Compact list of logical CPU ids, e.g. `[0, 1, 2, 5]` -> `"0-2,5"`. */
export const formatCoreList = (cores: number[]): string => {
  if (cores.length === 0) {
    return "";
  }

  const sorted = [...cores].sort((a, b) => a - b);
  const ranges: string[] = [];
  let start = sorted[0];
  let previous = sorted[0];

  for (const cpu of sorted.slice(1)) {
    if (cpu === previous + 1) {
      previous = cpu;
      continue;
    }
    ranges.push(start === previous ? `${start}` : `${start}-${previous}`);
    start = cpu;
    previous = cpu;
  }
  ranges.push(start === previous ? `${start}` : `${start}-${previous}`);

  return ranges.join(",");
};
