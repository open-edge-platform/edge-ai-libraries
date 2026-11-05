<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div v-if="libraryData" class="pool-container">
    <Table
      :table-data="libraryData.asset_pools"
      :library-data="libraryData"
      @create="handleCreate"
      @view="handleView"
      @search="handleSearch"
    />
    <CreateDialog
      v-if="createDialog"
      :library-data="libraryData"
      @close="handleCreateClose"
      @created="handleCreated"
      @search="handleSearch"
    />
    <DetailDrawer
      v-if="selectedPool"
      :drawer-data="selectedPool"
      :library-data="libraryData"
      @close="handleDetailClose"
      @search="handleSearch"
    />
  </div>
</template>
<script lang="ts" setup name="ConsoleAssetPool">
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import type { ConsolePageProps } from "../../types/console";
import Table from "./components/Table.vue";
import CreateDialog from "./components/CreateDialog.vue";
import DetailDrawer from "./components/DetailDrawer.vue";
const props = defineProps<ConsolePageProps>();
const emit = defineEmits<{ refresh: [] }>();
const route = useRoute();
const createDialog = ref(false);
const handleCreate = () => {
  createDialog.value = true;
};
const handleCreateClose = () => {
  createDialog.value = false;
};
const handleDetailClose = () => {
  selectedId.value = "";
};
const handleSearch = () => emit("refresh");
const selectedId = ref(
  typeof route.query.pool === "string" ? route.query.pool : "",
);
const selectedPool = computed(() =>
  props.libraryData?.asset_pools.find((pool) => pool.id === selectedId.value),
);
const handleView = (id: string) => {
  selectedId.value = id;
};
const handleCreated = (id: string) => {
  selectedId.value = id;
};
</script>
<style scoped lang="less">
.pool-container {
  min-width: 0;
}
</style>
