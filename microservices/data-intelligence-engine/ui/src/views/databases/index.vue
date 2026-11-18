<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="database-container">
    <div class="summary-strip">
      <div class="summary-item">
        <DatabaseOutlined class="summary-icon" />
        <span>{{ $t("console.databases") }}</span>
        <strong>{{ tableData.length }}</strong>
      </div>
      <div class="summary-item">
        <CheckCircleOutlined class="summary-icon success" />
        <span>{{ $t("console.reachable") }}</span>
        <strong>
          {{ Object.values(checkData).filter((item) => item.reachable).length }}
        </strong>
      </div>
      <div class="summary-item">
        <LinkOutlined class="summary-icon purple" />
        <span>{{ $t("console.inUse") }}</span>
        <strong>{{ tableData.filter((item) => item.in_use_by.length).length }}</strong>
      </div>
    </div>
    <Table
      :table-data="tableData"
      :check-data="checkData"
      :checking-ids="checkingIds"
      @create="handleCreate"
      @update="handleUpdate"
      @check="handleCheck"
      @check-all="handleCheckAll"
      @search="handleSearch"
    />
    <UpdateDialog
      v-if="updateDialog.visible"
      :dialog-data="updateDialog.data"
      @close="handleUpdateClose"
      @search="handleSearch"
    />
  </div>
</template>
<script lang="ts" setup name="ConsoleDatabase">
import { onMounted, reactive, ref } from "vue";
import {
  CheckCircleOutlined,
  DatabaseOutlined,
  LinkOutlined,
} from "@ant-design/icons-vue";
import {
  getDatabaseList,
  requestDatabaseCheck,
} from "@/api/console";
import type { Database, DatabaseCheck } from "@/api/console/type";
import Table from "./components/Table.vue";
import UpdateDialog from "./components/UpdateDialog.vue";
const tableData = ref<Database[]>([]);
const checkData = reactive<Record<string, DatabaseCheck>>({});
const checkingIds = ref<string[]>([]);
const updateDialog = reactive<{ visible: boolean; data?: Database }>({
  visible: false,
});
const queryDatabaseList = async () => {
  tableData.value = await getDatabaseList();
};
const handleCreate = () => {
  updateDialog.data = undefined;
  updateDialog.visible = true;
};
const handleUpdateClose = () => {
  updateDialog.visible = false;
};
const handleSearch = () => queryDatabaseList();
const handleUpdate = (id: string) => {
  updateDialog.data = tableData.value.find((item) => item.id === id);
  updateDialog.visible = true;
  delete checkData[id];
};
const handleCheck = async (id: string) => {
  checkingIds.value.push(id);
  delete checkData[id];
  try {
    checkData[id] = await requestDatabaseCheck(id);
  } finally {
    checkingIds.value = checkingIds.value.filter((item) => item !== id);
  }
};
const handleCheckAll = () =>
  Promise.all(tableData.value.map((item) => handleCheck(item.id)));
onMounted(queryDatabaseList);
</script>
