// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { Asset } from "@/api/console/type";

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
