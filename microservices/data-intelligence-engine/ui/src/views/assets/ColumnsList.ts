// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { TableColumnsType } from "ant-design-vue";
import type { Asset } from "@/api/console/type";

const getTableColumns = (
  t: (key: string) => string,
): TableColumnsType<Asset> => [
  { title: t("console.name"), key: "name", dataIndex: "name", width: 300 },
  { title: t("console.kind"), key: "kind", dataIndex: "kind", width: 140 },
  { title: t("console.pools"), key: "pools", width: 180 },
  { title: t("console.status"), key: "status", width: 160, fixed: "right" },
  { title: t("console.actions"), key: "actions", width: 190, fixed: "right" },
];
export default getTableColumns;
