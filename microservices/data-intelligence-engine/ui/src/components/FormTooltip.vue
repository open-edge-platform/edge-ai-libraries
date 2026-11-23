<!-- Copyright (C) 2025 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-tooltip placement="top" arrow-point-at-center>
    <template #title>
      {{ title }}
    </template>
    <InfoCircleOutlined
      class="form-tooltip-icon"
      :style="{ fontSize: size, color: 'var(--font-text-color)' }"
    />
  </a-tooltip>
</template>

<script setup lang="ts" name="FormTooltip">
import { InfoCircleOutlined } from "@ant-design/icons-vue";

defineProps({
  title: {
    type: String,
  },
  size: {
    type: String,
    default: () => "14px",
  },
});
</script>

<style lang="less" scoped>
.form-tooltip-icon {
  margin-inline-start: 6px;
}
</style>
