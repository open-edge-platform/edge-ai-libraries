// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { OutputMode } from "@/api/api.generated";

const STORAGE_KEY = "vippet.editorRunJob";
const OUTPUT_MODES: readonly OutputMode[] = ["disabled", "file", "live_stream"];

// Runs use an inline graph, so the backend job does not know which variant
// started it; this record lets the editor reattach after a reload.
export type EditorRunJob = {
  jobId: string;
  pipelineId: string;
  variantId: string;
  outputMode: OutputMode;
  metadataEnabled: boolean;
  latencyMetricsEnabled: boolean;
};

export const saveEditorRunJob = (job: EditorRunJob) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(job));
  } catch {
    // Storage unavailable: the run still works, it just cannot be resumed.
  }
};

export const loadEditorRunJob = (): EditorRunJob | null => {
  try {
    const parsed: unknown = JSON.parse(
      window.localStorage.getItem(STORAGE_KEY) ?? "null",
    );
    if (typeof parsed !== "object" || parsed === null) return null;

    const job = parsed as Record<string, unknown>;
    if (
      typeof job.jobId !== "string" ||
      typeof job.pipelineId !== "string" ||
      typeof job.variantId !== "string" ||
      !OUTPUT_MODES.includes(job.outputMode as OutputMode) ||
      typeof job.metadataEnabled !== "boolean" ||
      typeof job.latencyMetricsEnabled !== "boolean"
    ) {
      return null;
    }

    return job as EditorRunJob;
  } catch {
    return null;
  }
};

export const clearEditorRunJob = (jobId: string) => {
  if (loadEditorRunJob()?.jobId !== jobId) return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable: nothing to clear.
  }
};
