<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-tooltip :title="showDescription ? description : undefined" :trigger="['hover', 'focus']">
    <a-tag :color="color" :bordered="false" :tabindex="showDescription ? 0 : undefined" :aria-label="showDescription ? description : undefined">
      <template #icon>
        <span v-if="legend" class="status-dot" aria-hidden="true" />
        <ClockCircleOutlined v-else-if="expired" />
        <LoadingOutlined v-else-if="isIndexing(value)" spin />
        <CheckCircleOutlined v-else-if="value === 'ready'" />
        <CloseCircleOutlined v-else-if="value === 'failed'" />
      </template>
      {{ $te(`console.${value}`) ? $t(`console.${value}`) : value }}
    </a-tag>
  </a-tooltip>
</template>
<script lang="ts" setup>
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from "@ant-design/icons-vue";
import { isIndexing } from "../AssetProgress";

const props = withDefaults(
  defineProps<{ value: string; expired?: boolean; showDescription?: boolean; legend?: boolean }>(),
  { showDescription: true, legend: false },
);
const { t, te } = useI18n();
const color = computed(() => {
  if (props.expired || props.value === "text_ready") return "orange";
  if (props.value === "materializing") return "processing";
  if (props.value === "ready") return "success";
  if (props.value === "failed") return "error";
  return undefined;
});
const description = computed(() => {
  const key = `console.assetStatusHint.${props.value}`;
  const hint = te(key) ? t(key) : props.value;
  return props.expired ? `${hint} ${t("console.pollExpired")}` : hint;
});
</script>
<style scoped lang="less">
.status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 4px;
  border-radius: 50%;
  background-color: currentColor;
  vertical-align: middle;
}
</style>
