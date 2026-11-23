<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-drawer
    v-model:open="visible"
    :title="data.node?.title || data.node?.id || $t(data.edge ? 'console.graphRelationDetails' : 'console.details')"
    :root-style="{ zIndex: 1200 }"
    width="min(460px, 92vw)"
    @close="handleClose"
  >
    <template v-if="data.node">
      <a-descriptions :column="1" size="small" bordered>
        <a-descriptions-item label="ID">{{ data.node.id }}</a-descriptions-item>
        <a-descriptions-item :label="$t('console.type')">{{ data.node.label || "—" }}</a-descriptions-item>
        <a-descriptions-item :label="$t('console.origin')">
          {{ data.node.origin ? $t(`console.${data.node.origin}`) : "—" }}
        </a-descriptions-item>
        <a-descriptions-item :label="$t('console.graphDegree')">{{ data.node.degree }}</a-descriptions-item>
        <a-descriptions-item :label="$t('console.hop')">{{ data.concept?.hop ?? "—" }}</a-descriptions-item>
        <a-descriptions-item :label="$t('console.graphWeight')">{{ data.concept?.weight ?? "—" }}</a-descriptions-item>
      </a-descriptions>
      <h4>{{ $t("console.citations") }}</h4>
      <a-empty v-if="!data.citations.length" :description="$t('console.graphNoEvidence')" />
      <article v-for="entry in data.citations" :key="entry.id" class="graph-citation">
        <strong>{{ entry.chunk?.metadata.file_name || entry.id }}</strong>
        <small v-if="entry.chunk">{{ entry.id }}</small>
        <p>{{ entry.chunk?.text || $t("console.graphChunkUnavailable") }}</p>
      </article>
    </template>
    <a-descriptions v-else-if="data.edge" :column="1" size="small" bordered>
      <a-descriptions-item :label="$t('console.linkFrom')">{{ data.sourceName || data.edge.source }}</a-descriptions-item>
      <a-descriptions-item :label="$t('console.graphRelation')">{{ data.edge.relation }}</a-descriptions-item>
      <a-descriptions-item :label="$t('console.linkTo')">{{ data.targetName || data.edge.target }}</a-descriptions-item>
    </a-descriptions>
    <a-empty v-else :description="$t('console.graphFocusedMissing')" />
  </a-drawer>
</template>
<script lang="ts" setup name="GraphDetailDrawer">
import { computed, ref } from "vue";
import type { GraphDetailData } from "../Type";

const props = defineProps<{
  drawerData: GraphDetailData;
}>();
const emit = defineEmits<{ close: [] }>();
const handleClose = () => emit("close");
const visible = ref(true);
const data = computed(() => props.drawerData);
</script>
<style scoped lang="less">
.graph-citation {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-main-color);
  overflow-wrap: anywhere;
  strong,
  small {
    display: block;
  }
  small {
    color: var(--font-info-color);
  }
  p {
    white-space: pre-wrap;
    margin: 8px 0 0;
  }
}
</style>
