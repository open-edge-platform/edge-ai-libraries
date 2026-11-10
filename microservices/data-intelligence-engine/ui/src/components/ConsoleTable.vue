<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="console-table">
    <div ref="scrollArea" class="table-scroll">
      <a-table
        v-bind="$attrs"
        :data-source="pageData"
        :pagination="false"
        :sticky="{ getContainer: getTableScrollContainer }"
        size="small"
      >
        <template v-for="(_, name) in $slots" #[name]="scope">
          <slot :name="name" v-bind="scope" />
        </template>
      </a-table>
    </div>
    <div v-if="dataSource.length > 10" class="table-footer">
      <a-pagination
        :current="current"
        :page-size="pageSize"
        :total="dataSource.length"
        :page-size-options="['10', '20', '50', '100']"
        :show-total="(total) => $t('console.totalRecords', { count: total })"
        showSizeChanger
        showLessItems
        size="small"
        @change="handlePageChange"
      />
    </div>
  </div>
</template>
<script lang="ts" setup generic="T extends object">
import { computed, ref, watch } from "vue";

defineOptions({ inheritAttrs: false });
const props = defineProps<{ dataSource: T[]; resetKey?: string }>();
const current = ref(1);
const pageSize = ref(10);
const scrollArea = ref<HTMLElement>();
const getTableScrollContainer = () => scrollArea.value || window;
const pageData = computed(() =>
  props.dataSource.slice(
    (current.value - 1) * pageSize.value,
    current.value * pageSize.value,
  ),
);
const handlePageChange = (page: number, size: number) => {
  current.value = size === pageSize.value ? page : 1;
  pageSize.value = size;
};
watch(
  () => props.resetKey,
  () => {
    current.value = 1;
  },
);
watch(
  () => props.dataSource.length,
  (total) => {
    current.value = Math.min(
      current.value,
      Math.max(1, Math.ceil(total / pageSize.value)),
    );
  },
);
watch([current, pageSize], () => scrollArea.value?.scrollTo(0, 0));
</script>
<style scoped lang="less">
.console-table {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 0 16px;
}
.table-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  :deep(.intel-table-thead > tr > th) {
    padding: 8px 12px !important;
    font-size: 12px;
  }
  :deep(.intel-table-tbody > tr > td) {
    padding: 7px 12px;
    line-height: 20px;
    font-size: 13px;
  }
}
.table-footer {
  flex-shrink: 0;
  padding: 10px 16px;
  border-top: 1px solid var(--border-main-color);
  background: var(--bg-content-color);
  :deep(.intel-pagination) {
    margin: 0;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px 0;
  }
}
</style>
