<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-drawer
    v-model:open="drawerVisible"
    :title="$t('console.assetDetails')"
    width="min(540px, 100vw)"
    @close="handleClose"
  >
    <div class="asset-heading">
      <div class="asset-icon"><FileTextOutlined /></div>
      <div>
        <h3>{{ drawerData.name || drawerData.id }}</h3>
        <StatusTag :value="drawerData.kind" />
        <AssetStatus
          :value="drawerData.materialization || 'unknown'"
          :expired="drawerData.progressExpired"
        />
      </div>
    </div>
    <a-descriptions :column="1" bordered size="small">
      <a-descriptions-item :label="$t('console.id')">
        <a-typography-text copyable>{{ drawerData.id }}</a-typography-text>
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.origin')">
        {{ drawerData.origin }}
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.mediaType')">
        {{ drawerData.media_type || "—" }}
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.contentSource')">
        {{
          libraryData.sources.find(
            (source) => source.id === drawerData.content_source_id,
          )?.name ||
          drawerData.content_source_id ||
          "—"
        }}
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.pools')">
        <a-tag v-for="id in drawerData.asset_pool_ids" :key="id">
          {{
            libraryData.asset_pools.find((pool) => pool.id === id)?.name || id
          }}
        </a-tag>
        <span v-if="!drawerData.asset_pool_ids.length">—</span>
      </a-descriptions-item>
    </a-descriptions>
  </a-drawer>
</template>
<script lang="ts" setup name="DetailDrawer">
import { ref } from "vue";
import { FileTextOutlined } from "@ant-design/icons-vue";
import type { Library } from "@/api/console/type";
import type { AssetRow } from "../AssetProgress";
import StatusTag from "../../../components/StatusTag.vue";
import AssetStatus from "./AssetStatus.vue";
defineProps<{ drawerData: AssetRow; libraryData: Library }>();
const emit = defineEmits<{ close: [] }>();
const handleClose = () => emit("close");
const drawerVisible = ref(true);
</script>
<style scoped lang="less">
.asset-heading {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 0 24px;
  h3 {
    margin: 0 0 8px;
    color: var(--font-main-color);
  }
}
.asset-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 60px;
  background: var(--bg-card-color);
  border-radius: 8px;
  font-size: 26px;
  color: var(--color-primary-second);
}
</style>
