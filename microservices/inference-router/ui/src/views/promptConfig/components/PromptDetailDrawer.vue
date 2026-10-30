<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-drawer
    :open="true"
    :title="t('router.routerPromptDetailTitle')"
    placement="right"
    :width="420"
    class="router-prompt-detail-drawer"
    @close="emit('close')"
  >
    <ul class="prompt-detail-list">
      <li>
        <span>{{ t("router.routerPromptStatus") }}</span>
        <strong :class="prompt.active ? 'is-active' : 'is-inactive'">
          {{
            prompt.active
              ? t("router.routerPromptActive")
              : t("router.routerPromptInactive")
          }}
        </strong>
      </li>
      <li>
        <span>{{ t("router.routerPromptModel") }}</span>
        <strong>{{ prompt.model }}</strong>
      </li>
      <li v-if="prompt.version">
        <span>{{ t("router.routerPromptVersion") }}</span>
        <strong>{{ prompt.version }}</strong>
      </li>
      <li class="prompt-content-item">
        <span>{{ t("router.routerPromptContent") }}</span>
        <strong>{{ prompt.content }}</strong>
      </li>
    </ul>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { ConfigPromptRow } from "@/types/router";

const props = withDefaults(
  defineProps<{
    drawerData?: ConfigPromptRow;
  }>(),
  {
    drawerData: () => ({}),
  },
);

const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const prompt = computed(() => props.drawerData);
</script>

<style scoped lang="less">
.prompt-detail-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.prompt-detail-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
}
.prompt-detail-list span {
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
.prompt-detail-list strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
}
.prompt-detail-list .prompt-content-item {
  display: grid;
  align-items: start;
}
.prompt-content-item strong {
  overflow: visible;
  text-overflow: clip;
  white-space: pre-wrap;
  word-break: break-word;
}
.prompt-detail-list strong.is-active {
  color: var(--color-success);
}
.prompt-detail-list strong.is-inactive {
  color: var(--font-tip-color);
}
</style>
