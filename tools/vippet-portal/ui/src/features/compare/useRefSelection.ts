import { useCallback, useMemo, useState } from "react";

/** Multi-select of result refs used to drive every comparison view. */
export const useRefSelection = (limit = 6) => {
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = useCallback(
    (ref: string) =>
      setSelected((current) =>
        current.includes(ref)
          ? current.filter((item) => item !== ref)
          : current.length >= limit
            ? current
            : [...current, ref],
      ),
    [limit],
  );

  const clear = useCallback(() => setSelected([]), []);

  const isSelected = useCallback(
    (ref: string) => selected.includes(ref),
    [selected],
  );

  const compareHref = useCallback(
    (basePath: string) =>
      `${basePath}/compare?${selected.map((ref) => `refs=${encodeURIComponent(ref)}`).join("&")}`,
    [selected],
  );

  return useMemo(
    () => ({ selected, toggle, clear, isSelected, compareHref, limit }),
    [selected, toggle, clear, isSelected, compareHref, limit],
  );
};
