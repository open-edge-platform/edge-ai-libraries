<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div v-if="libraryData" class="source-container">
    <Table
      :table-data="libraryData.sources"
      :library-data="libraryData"
      @create="handleCreate"
      @view="handleView"
      @search="handleSearch"
    />
    <CreateDialog
      v-if="createDialog"
      :library-data="libraryData"
      @close="handleCreateClose"
      @search="handleSearch"
    />
    <DetailDrawer
      v-if="selectedSource"
      :drawer-data="selectedSource"
      :library-data="libraryData"
      @close="handleDetailClose"
      @search="handleSearch"
    />
  </div>
</template>
<script lang="ts" setup name="ConsoleSource">
import { computed, ref } from "vue";
import type { ConsolePageProps } from "../../types/console";
import Table from "./components/Table.vue";
import CreateDialog from "./components/CreateDialog.vue";
import DetailDrawer from "./components/DetailDrawer.vue";
const props = defineProps<ConsolePageProps>();
const emit = defineEmits<{ refresh: [] }>();
const createDialog = ref(false);
const selectedId = ref("");
const handleCreate = () => {
  createDialog.value = true;
};
const handleCreateClose = () => {
  createDialog.value = false;
};
const handleDetailClose = () => {
  selectedId.value = "";
};
const handleView = (id: string) => {
  selectedId.value = id;
};
const handleSearch = () => emit("refresh");
const selectedSource = computed(() =>
  props.libraryData?.sources.find((item) => item.id === selectedId.value),
);
</script>
<style scoped lang="less">
.source-container {
  min-width: 0;
}
</style>
