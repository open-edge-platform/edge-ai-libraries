import { useCallback, type Dispatch, type SetStateAction } from "react";

type StreamRateSelection = {
  pipelineId: string;
  stream_rate: number;
};

const allocateProportionally = (weights: number[], total: number): number[] => {
  if (weights.length === 0) return [];

  const safeTotal = Math.max(0, total);
  const nonNegativeWeights = weights.map((weight) => Math.max(0, weight));
  const weightSum = nonNegativeWeights.reduce((sum, weight) => sum + weight, 0);
  const effectiveWeights =
    weightSum > 0
      ? nonNegativeWeights
      : new Array(nonNegativeWeights.length).fill(1);
  const effectiveSum = effectiveWeights.reduce(
    (sum, weight) => sum + weight,
    0,
  );

  const raw = effectiveWeights.map(
    (weight) => (weight / effectiveSum) * safeTotal,
  );
  const allocated = raw.map((value) => Math.floor(value));

  let remainder = safeTotal - allocated.reduce((sum, value) => sum + value, 0);
  if (remainder > 0) {
    const byFractionDesc = raw
      .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
      .sort((a, b) => {
        if (b.fraction === a.fraction) return a.index - b.index;
        return b.fraction - a.fraction;
      });

    for (let i = 0; i < byFractionDesc.length && remainder > 0; i++) {
      allocated[byFractionDesc[i].index] += 1;
      remainder -= 1;
    }
  }

  return allocated;
};

export const rebalanceStreamRates = <T extends StreamRateSelection>(
  selections: T[],
  changedRowIndex: number,
  newRate: number,
): T[] => {
  if (selections.length === 1) {
    return [{ ...selections[0], stream_rate: 100 }];
  }

  if (changedRowIndex < 0 || changedRowIndex >= selections.length)
    return selections;

  let lockedSum = 0;
  if (changedRowIndex === selections.length - 1) {
    for (let index = 1; index < selections.length - 1; index++) {
      lockedSum += selections[index].stream_rate;
    }
  } else {
    for (let index = 0; index < changedRowIndex; index++) {
      lockedSum += selections[index].stream_rate;
    }
  }

  const maxAllowedRate = Math.max(0, 100 - lockedSum);
  const clampedRate = Math.max(0, Math.min(maxAllowedRate, newRate));

  const remainingRate = Math.max(0, 100 - lockedSum - clampedRate);

  const selectionsToAdjust =
    changedRowIndex === selections.length - 1
      ? [selections[0]]
      : selections.slice(changedRowIndex + 1);

  const allocatedRates = allocateProportionally(
    selectionsToAdjust.map((selection) => selection.stream_rate),
    remainingRate,
  );

  const adjusted = selectionsToAdjust.map((selection, index) => ({
    ...selection,
    stream_rate: allocatedRates[index],
  }));

  return selections.map((selection, index) => {
    if (index === changedRowIndex) {
      return { ...selection, stream_rate: clampedRate };
    }

    if (changedRowIndex === selections.length - 1 && index === 0) {
      return adjusted[0];
    }

    if (changedRowIndex !== selections.length - 1 && index > changedRowIndex) {
      const adjustedIndex = index - changedRowIndex - 1;
      return adjusted[adjustedIndex];
    }

    return selection;
  });
};

export const useStreamRateChange = <T extends StreamRateSelection>(
  setSelections: Dispatch<SetStateAction<T[]>>,
) => {
  return useCallback(
    (changedRowIndex: number, newRate: number) => {
      setSelections((prev) =>
        rebalanceStreamRates(prev, changedRowIndex, newRate),
      );
    },
    [setSelections],
  );
};
