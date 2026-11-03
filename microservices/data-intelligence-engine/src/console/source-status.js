// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
// Keep display readiness independent of projection-sync bookkeeping.
(function (root) {
  "use strict";
  const labels = {
    ready: "ready", failed: "failed", pending: "pending", indexing: "indexing",
    extracting: "Extracting…", extraction_waiting: "Extraction waiting",
    extraction_queued: "Extraction queued", extraction_pending: "Extraction needed",
    extraction_failed: "Extraction failed", unconfigured: "No sources",
  };
  function source(status) {
    if (status.display_status) return status.display_status;
    if (status.status !== "ready" || !status.extraction) return status.status;
    const x = status.extraction;
    if (x.state === "running") return "extracting";
    if (x.state === "queued") return x.active?.not_before ? "extraction_waiting" : "extraction_queued";
    if (x.outdated) return x.last?.state === "failed" ? "extraction_failed" : "extraction_pending";
    return "ready";
  }
  function pool(value) {
    if (value.display_status) return value.display_status;
    const states = (value.source_statuses || []).map(source);
    for (const state of ["failed", "extraction_failed", "indexing", "extracting", "extraction_waiting", "extraction_queued", "pending", "extraction_pending"]) {
      if (states.includes(state)) return state;
    }
    return states.length ? "ready" : "unconfigured";
  }
  function appearance(state) {
    const cls = ["failed", "extraction_failed"].includes(state) ? "bad"
      : state === "ready" ? "ok" : state === "unconfigured" ? "" : "warn";
    return { state, label: labels[state] || state, cls };
  }
  root.SourceStatus = { source, pool, appearance };
})(globalThis);