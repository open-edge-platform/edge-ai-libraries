// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { Asset, IngestResult } from "../../api/console/type";

export interface AssetRow extends Asset {
  pending?: boolean;
  progressExpired?: boolean;
}

interface ProgressEntry {
  asset: Asset;
  registered: boolean;
  startedAt: number;
  expired: boolean;
  revision: number;
  uploaded: boolean;
}

export const isIndexing = (phase: Asset["materialization"]) =>
  phase === "materializing" || phase === "text_ready";

export class AssetProgress {
  listed: Asset[] = [];
  entries = new Map<string, ProgressEntry>();
  revision = 0;

  get rows(): AssetRow[] {
    return [
      ...[...this.entries.values()]
        .reverse()
        .sort((a, b) => Number(b.uploaded) - Number(a.uploaded))
        .map((entry) => ({
        ...entry.asset,
        pending: !entry.registered,
        progressExpired: entry.expired,
      })),
      ...this.listed.filter((asset) => !this.entries.has(asset.id)),
    ];
  }

  get trackedIds(): string[] {
    return [...this.entries]
      .filter(([, entry]) => !entry.expired && (
        isIndexing(entry.asset.materialization) ||
        (!entry.registered && entry.asset.materialization === "ready")
      ))
      .map(([id]) => id);
  }

  accept(result: IngestResult, now = Date.now()): void {
    const revision = ++this.revision;
    // Reverse insertion keeps the response's file order within each new batch.
    [...result.asset_ids].reverse().forEach((id, reverseIndex) => {
      const index = result.asset_ids.length - reverseIndex - 1;
      const path = result.file_paths[index];
      this.entries.delete(id);
      this.entries.set(id, {
        asset: {
          id,
          name: path ? path.split(/[\\/]/).pop() || path : `Inline text ${id.slice(0, 8)}`,
          origin: path || "",
          kind: path ? "file" : "text",
          media_type: "",
          content_source_id: result.content_source_id,
          asset_pool_ids: [...result.asset_pool_ids],
          materialization: result.status,
        },
        registered: false,
        startedAt: now,
        expired: false,
        revision,
        uploaded: true,
      });
    });
  }

  update(
    assets: Asset[] | undefined,
    phases: Record<string, Asset["materialization"]> | undefined,
    revision: number,
    now = Date.now(),
  ): void {
    const byId = new Map(assets?.map((asset) => [asset.id, asset]));
    if (assets) {
      this.listed = assets;
      for (const asset of assets) {
        if (!this.entries.has(asset.id) && isIndexing(asset.materialization)) {
          this.entries.set(asset.id, {
            asset,
            registered: true,
            startedAt: now,
            expired: false,
            revision,
            uploaded: false,
          });
        }
      }
    }
    for (const [id, entry] of this.entries) {
      // A response started before a new upload must not overwrite its progress.
      if (entry.revision > revision) continue;
      const listed = byId.get(id);
      if (assets && entry.registered && !listed) {
        this.entries.delete(id);
        continue;
      }
      const phase = phases && Object.prototype.hasOwnProperty.call(phases, id)
        ? phases[id]
        : listed ? listed.materialization : entry.asset.materialization;
      entry.asset = { ...(listed || entry.asset), materialization: phase };
      if (listed) entry.registered = true;
      if (!isIndexing(phase) && (entry.registered || phase !== "ready"))
        entry.expired = false;
    }
  }

  expire(now = Date.now()): number {
    let count = 0;
    for (const id of this.trackedIds) {
      const entry = this.entries.get(id)!;
      if (now - entry.startedAt >= 600000) {
        entry.expired = true;
        count++;
      }
    }
    return count;
  }

  resume(now = Date.now()): void {
    for (const entry of this.entries.values()) {
      if (entry.expired) {
        entry.expired = false;
        entry.startedAt = now;
      }
    }
  }

  remove(ids: string[]): void {
    for (const id of ids) this.entries.delete(id);
    this.listed = this.listed.filter((asset) => !ids.includes(asset.id));
  }
}
