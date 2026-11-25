<template>
  <h3>{{ libraryData.name }}</h3>
  <a-descriptions :column="1" bordered size="small">
    <a-descriptions-item :label="$t('console.description')">{{
      libraryData.description || $t("console.noDescription")
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.assets')">{{
      libraryData.asset_count
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.documents')">{{
      libraryData.document_count
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.chunks')">{{
      libraryData.chunk_count
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.pools')">{{
      libraryData.asset_pools.length
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.sources')">{{
      libraryData.sources.length
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.contentDatabase')">{{
      libraryData.content_database || "—"
    }}</a-descriptions-item>
  </a-descriptions>
  <p class="console-info-hint detail-notice">
    <InfoCircleOutlined />
    <span>{{ $t("console.canvasInteractionHint") }}</span>
  </p>
  <a-button type="primary" @click="emit('retrieve')">{{
    $t("console.retrieve")
  }}</a-button>
</template>
<script lang="ts" setup name="CanvasLibraryDetails">
import { InfoCircleOutlined } from "@ant-design/icons-vue";
import type { Library } from "@/api/console/type";

defineProps<{ libraryData: Library }>();
const emit = defineEmits<{ retrieve: [] }>();
</script>
<style scoped lang="less">
.detail-notice {
  margin: 16px 0;
}
</style>
