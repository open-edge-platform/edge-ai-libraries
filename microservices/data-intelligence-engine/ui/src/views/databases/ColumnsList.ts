// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { TableColumnsType } from "ant-design-vue";
import type { Database } from "@/api/console/type";

const getTableColumns = (
  t: (key: string) => string,
): TableColumnsType<Database> => [
  { title: t("console.database"), key: "name", dataIndex: "id", width: 190 },
  { title: t("console.options"), key: "options", width: 260 },
  { title: t("console.inUseBy"), key: "inUseBy", width: 180 },
  { title: t("console.status"), key: "status", width: 160 },
  { title: t("console.actions"), key: "actions", width: 260, fixed: "right" },
];
export default getTableColumns;
