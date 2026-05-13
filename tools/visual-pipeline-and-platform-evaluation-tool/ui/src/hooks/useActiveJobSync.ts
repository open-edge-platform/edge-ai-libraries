// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";
import { useAppDispatch } from "@/store/hooks";
import { setActiveJobId } from "@/store/reducers/metrics";

/**
 * Syncs the given job ID to Redux so that metric selectors (FPS, latency)
 * filter for the currently running job and ignore stale values from
 * previous runs.
 */
export function useActiveJobSync(jobId: string | null | undefined) {
  const dispatch = useAppDispatch();
  useEffect(() => {
    dispatch(setActiveJobId(jobId ?? null));
    return () => {
      dispatch(setActiveJobId(null));
    };
  }, [jobId, dispatch]);
}
