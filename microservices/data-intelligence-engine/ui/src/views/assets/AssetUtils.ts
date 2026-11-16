// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { reactive } from "vue";
import { getAssetList, getAssetMaterialization } from "@/api/console";
import type { Asset, AssetPage } from "@/api/console/type";
import { AssetProgress } from "./AssetProgress";

export function getAssetKind(asset: Pick<Asset, "kind" | "media_type" | "name" | "origin">): string {
  if (["document", "image", "video", "audio", "okf"].includes(asset.kind))
    return asset.kind;
  const mediaType = asset.media_type.toLowerCase();
  for (const kind of ["image", "video", "audio"])
    if (mediaType.startsWith(`${kind}/`)) return kind;
  const extension = (asset.name || asset.origin).toLowerCase().split(/[?#]/)[0].split(".").pop();
  if (extension && ["png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "svg", "heic"].includes(extension))
    return "image";
  if (extension && ["mp4", "mov", "mkv", "avi", "webm", "m4v", "mpeg", "mpg"].includes(extension))
    return "video";
  if (extension && ["mp3", "wav", "flac", "ogg", "m4a", "aac", "opus", "wma"].includes(extension))
    return "audio";
  if (asset.kind === "file" || asset.kind === "text" || mediaType.startsWith("text/"))
    return "document";
  return asset.kind;
}

export const collectAssets = async (
  fetchPage: (page: number) => Promise<AssetPage>,
  incompleteError: () => Error,
): Promise<Asset[]> => {
  const assets: Asset[] = [];
  let page = 1;
  let total: number;
  do {
    const data = await fetchPage(page++);
    assets.push(...data.assets);
    total = data.total;
    if (!data.assets.length && assets.length < total)
      throw incompleteError();
  } while (assets.length < total);
  return assets;
};

export interface StagedFile {
  file: File;
  path: string;
}

export const readDroppedFiles = async (
  data: DataTransfer,
): Promise<StagedFile[]> => {
  // Capture entries before the drop event returns; the browser then protects its data store.
  const entries = Array.from(data.items)
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry !== null);
  const files = Array.from(data.files);
  const staged: StagedFile[] = [];
  const walk = async (entry: FileSystemEntry): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) =>
        (entry as FileSystemFileEntry).file(resolve, reject),
      );
      staged.push({ file, path: entry.fullPath.replace(/^\/+/, "") });
    } else {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      let batch: FileSystemEntry[];
      do {
        batch = await new Promise<FileSystemEntry[]>((resolve, reject) =>
          reader.readEntries(resolve, reject),
        );
        for (const child of batch) await walk(child);
      } while (batch.length);
    }
  };
  for (const entry of entries) await walk(entry);
  return entries.length
    ? staged
    : files.map((file) => ({ file, path: file.name }));
};

// Keep accepted assets across page remounts in this tab.
const libraries = new Map<string, AssetProgress>();

export function getAssetProgress(library: string): AssetProgress {
  let progress = libraries.get(library);
  if (!progress) {
    progress = reactive(new AssetProgress());
    libraries.set(library, progress);
  }
  return progress;
}

export async function syncAssetProgress(
  library: string,
  progress: AssetProgress,
  incompleteError: () => Error,
  onListed: () => void,
  isActive: () => boolean,
  showLoading = false,
): Promise<void> {
  const revision = progress.revision;
  const ids = showLoading ? [...progress.entries.keys()] : progress.trackedIds;
  const phaseRequests: Promise<Record<string, Asset["materialization"]>>[] = [];
  for (let index = 0; index < ids.length; index += 50) {
    phaseRequests.push(getAssetMaterialization(library, ids.slice(index, index + 50)));
  }
  const [assets, phases] = await Promise.allSettled([
    collectAssets(
      (page) => getAssetList(library, { page_num: page, page_size: 500 }, showLoading && page === 1),
      incompleteError,
    ),
    Promise.all(phaseRequests).then((batches) =>
      batches.reduce<Record<string, Asset["materialization"]>>(
        (result, batch) => Object.assign(result, batch), {},
      ),
    ),
  ]);
  if (!isActive()) return;
  progress.update(
    assets.status === "fulfilled" ? assets.value : undefined,
    phases.status === "fulfilled" ? phases.value : undefined,
    revision,
  );
  if (assets.status === "fulfilled") onListed();
  if (assets.status === "rejected") throw assets.reason;
  if (phases.status === "rejected") throw phases.reason;
}
