<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div
    class="resource-card"
    :class="[node.kind, { compact, selected }]"
    :style="{ '--resource-color': resourceCategories[node.kind].color }"
  >
    <div class="resource-heading">
      <span class="resource-icon"
        ><component :is="resourceCategories[node.kind].icon"
      /></span>
      <div class="resource-title">
        <strong :title="node.name">{{ node.name }}</strong>
      </div>
      <a-tag
        v-if="node.kind !== 'pool'"
        :bordered="false"
        class="resource-type-tag"
        :title="node.content ? $t('console.defaultContent') : typeLabel"
        >{{ typeLabel }}</a-tag
      >
    </div>
    <template v-if="!compact">
      <div class="resource-meta">
        <template v-if="node.kind === 'asset'">
          <span>{{ $t("console.pools") }} {{ node.poolCount }}</span>
          <span :title="node.mediaType">{{ node.mediaType || typeLabel }}</span>
        </template>
        <template v-else-if="node.kind === 'pool'">
          <span>{{ $t("console.assets") }} {{ node.assetCount }}</span>
          <span>{{ $t("console.sources") }} {{ node.sourceCount }}</span>
          <span>r{{ node.revision }}</span>
        </template>
        <span v-else :title="`${node.database} / ${node.collection}`">
          {{ node.database }} / {{ node.collection }}
        </span>
      </div>
      <div class="resource-status" :title="node.error">
        <AssetStatus
          v-if="node.kind === 'asset'"
          :value="node.status"
          :expired="node.progressExpired"
        />
        <StatusTag v-else :value="node.status" />
        <StatusTag
          v-if="node.validationStatus && node.validationStatus !== node.status"
          :value="node.validationStatus"
        />
        <a-tag
          v-if="node.content"
          :bordered="false"
          class="resource-type-tag"
          :title="$t('console.defaultContent')"
        >
          {{ $t("console.defaultContent") }}
        </a-tag>
      </div>
    </template>
  </div>
</template>
<script lang="ts" setup>
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import StatusTag from "../../../components/StatusTag.vue";
import AssetStatus from "../../assets/components/AssetStatus.vue";
import type { CanvasNode } from "../Type";
import { resourceCategories } from "../ResourcePresentation";

const props = defineProps<{
  node: CanvasNode;
  compact?: boolean;
  selected?: boolean;
}>();
const { t, te } = useI18n();
const typeLabel = computed(() => {
  const key =
    props.node.kind === "pool"
      ? "pools"
      : props.node.kind === "source"
        ? `${props.node.resourceType}Source`
        : props.node.resourceType === "asset"
          ? "assets"
          : props.node.resourceType;
  return te(`console.${key}`) ? t(`console.${key}`) : props.node.resourceType;
});
</script>
<style scoped lang="less">
.resource-card {
  height: 100%;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--border-main-color);
  border-left: 3px solid var(--resource-color);
  border-radius: 8px;
  background: var(--bg-content-color);
  box-shadow: 0 2px 6px var(--bg-box-shadow);
  &.selected {
    border-color: var(--resource-color);
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--resource-color) 16%, transparent);
  }
  &.compact {
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
    .resource-icon {
      width: 24px;
      height: 24px;
      font-size: 15px;
    }
    .resource-title strong {
      font-size: 12px;
      line-height: 20px;
    }
  }
}
.resource-heading {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.resource-icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  color: var(--resource-color);
  background: color-mix(in srgb, var(--resource-color) 9%, transparent);
  font-size: 14px;
}
.resource-title {
  flex: 1;
  min-width: 0;
  strong {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--font-main-color);
    font-weight: 500;
    font-size: 13px;
    line-height: 21px;
  }
}
.resource-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  color: var(--font-info-color);
  font-size: 11px;
  line-height: 18px;
  > span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
.resource-status {
  display: flex;
  gap: 4px;
  margin-top: 5px;
  :deep(.intel-tag) {
    margin: 0;
    padding: 0 5px;
    font-size: 10px;
    line-height: 18px;
  }
}
.resource-type-tag {
  flex-shrink: 0;
  max-width: 85px;
  margin: 0;
  padding: 0 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  line-height: 16px;
  color: var(--resource-color);
  background: color-mix(in srgb, var(--resource-color) 9%, transparent);
}
</style>
