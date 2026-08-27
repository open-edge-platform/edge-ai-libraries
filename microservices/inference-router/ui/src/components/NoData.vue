<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div class="no-data-wrap">
    <a-empty :image="notFound" :description="resolvedDescription" />
  </div>
</template>

<script setup lang="ts" name="NoData">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import notFound from "@/assets/images/noData.png";

const props = defineProps({
  description: {
    type: String,
    default: "",
  },
});

const { t } = useI18n();

const resolvedDescription = computed(() => {
  return props.description || t("common.emptyText");
});
</script>

<style scoped lang="less">
.no-data-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}
</style>
