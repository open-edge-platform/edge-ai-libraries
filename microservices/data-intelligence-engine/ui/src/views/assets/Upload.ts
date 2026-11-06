// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
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
