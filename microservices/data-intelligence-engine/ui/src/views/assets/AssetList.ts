// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
import type { Asset, AssetPage } from "../../api/console/type";

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
