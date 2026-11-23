<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-spin :spinning="loading">
    <div class="results-container">
      <a-alert
        v-if="result?.postprocess_error"
        type="warning"
        showIcon
        :message="$t('console.rerankFailed')"
        :description="result.postprocess_error"
        class="notice-wrap"
      />
      <div v-if="result" class="results-summary">
        <span>
          {{
            $t("console.resultCount", {
              count: result.chunks.length,
              total: result.retrieved_chunks.length,
            })
          }}
        </span>
        <a-tag :bordered="false">{{ result.libraries.join(", ") }}</a-tag>
      </div>
      <a-empty
        v-if="!result"
        :description="$t('console.noResults')"
        class="empty-wrap"
      />
      <a-empty v-else-if="!result.chunks.length" class="empty-wrap" />
      <article
        v-for="(chunk, index) in result?.chunks"
        :id="`console-result-${index + 1}`"
        :key="chunk.id"
        class="result-item"
      >
        <div class="result-heading">
          <span class="rank-wrap">
            {{ String(index + 1).padStart(2, "0") }}
          </span>
          <div class="result-name">
            <strong>
              {{
                chunk.metadata.file_name || chunk.metadata.library || chunk.id
              }}
            </strong>
            <div>
              <span v-if="chunk.metadata.page != null">
                p.{{ chunk.metadata.page }} ·
              </span>
              {{ chunk.metadata.pool_id || chunk.metadata.source_id }}
            </div>
          </div>
          <a-tag class="theme-tag-primary" :bordered="false">
            {{ chunk.score.toFixed(5) }}
          </a-tag>
          <a-button
            size="small"
            danger
            :disabled="excludedIds?.includes(chunk.id)"
            :aria-label="
              $t(
                excludedIds?.includes(chunk.id)
                  ? 'console.excluded'
                  : 'console.exclude',
              )
            "
            @click="handleExclude(chunk.id)"
          >
            <template #icon>
              <CheckOutlined v-if="excludedIds?.includes(chunk.id)" />
              <StopOutlined v-else />
            </template>
            {{
              $t(
                excludedIds?.includes(chunk.id)
                  ? "console.excluded"
                  : "console.exclude",
              )
            }}
          </a-button>
        </div>
        <div
          v-if="chunk.metadata.media_key && chunk.metadata.library"
          class="media-wrap"
        >
          <a-image
            v-if="chunk.metadata.kind === 'image'"
            :src="getMediaUrl(chunk)"
            :alt="chunk.text"
            :width="260"
          />
          <video
            v-else-if="chunk.metadata.kind === 'video'"
            controls
            preload="metadata"
            :src="getMediaUrl(chunk)"
          />
          <audio
            v-else-if="chunk.metadata.kind === 'audio'"
            controls
            preload="metadata"
            :src="getMediaUrl(chunk)"
          />
        </div>
        <div
          class="result-text intel-markdown"
          v-html="renderMarkdown(chunk.text)"
          @click="handleImageClick"
        ></div>
        <div
          v-if="conceptList.some((item) => item.chunkId === chunk.id)"
          class="concept-wrap"
        >
          <NodeIndexOutlined />
          <span>{{ $t("console.viaConcepts") }}</span>
          <a-tag
            v-for="concept in conceptList.filter(
              (item) => item.chunkId === chunk.id,
            )"
            :key="`${concept.pool}:${concept.id}`"
            class="concept-tag"
            @click="handleFocus({ pool: concept.pool, id: concept.id })"
          >
            {{ concept.id }}
            <ExportOutlined />
          </a-tag>
        </div>
      </article>
      <a-image
        :style="{ display: 'none' }"
        :src="imageSrc"
        :preview="{
          visible: imageVisible,
          onVisibleChange: handleImageVisible,
        }"
      />
    </div>
  </a-spin>
</template>
<script lang="ts" setup name="Results">
import { computed, ref } from "vue";
import {
  ExportOutlined,
  CheckOutlined,
  NodeIndexOutlined,
  StopOutlined,
} from "@ant-design/icons-vue";
import { blobUrl } from "@/api/console";
import type { Chunk, RetrieveResult } from "@/api/console/type";
import { marked } from "marked";
import CustomRenderer from "@/utils/customRenderer";
import type { ConceptFocus } from "../Type";
const props = defineProps<{
  result?: RetrieveResult;
  loading?: boolean;
  excludedIds?: string[];
}>();
const emit = defineEmits<{
  exclude: [id: string];
  focus: [value: ConceptFocus];
}>();
const conceptList = computed(
  () =>
    props.result?.graph_traces?.flatMap((trace) =>
      trace.concepts.flatMap((concept) =>
        concept.hit_chunk_ids.map((chunkId) => ({
          pool: trace.asset_pool_id,
          id: concept.id,
          chunkId,
        })),
      ),
    ) || [],
);
const handleExclude = (id: string) => emit("exclude", id);
const handleFocus = (focus: ConceptFocus) => emit("focus", focus);
const imageSrc = ref("");
const imageVisible = ref(false);
const handleImageVisible = (visible: boolean) => (imageVisible.value = visible);
const handleImageClick = (event: MouseEvent) => {
  if (!(event.target instanceof HTMLImageElement)) return;
  imageSrc.value = event.target.src;
  imageVisible.value = true;
};
const renderMarkdown = (text: string) =>
  marked.parse(text, { renderer: CustomRenderer, async: false });
const getMediaUrl = (chunk: Chunk) => {
  const metadata = chunk.metadata;
  const url = `${blobUrl}?${new URLSearchParams({ library: metadata.library!, media_key: metadata.media_key! })}`;
  if (metadata.t_start_ms == null) return url;
  return `${url}#t=${metadata.t_start_ms / 1000}${metadata.t_end_ms != null ? `,${metadata.t_end_ms / 1000}` : ""}`;
};
</script>
<style scoped lang="less">
.empty-wrap {
  padding: 50px 10px;
}
.results-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--font-info-color);
  font-size: 12px;
  margin-bottom: 16px;
}
.result-item {
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  padding: 18px;
  margin-bottom: 14px;
  scroll-margin-top: 20px;
  &:last-child {
    margin-bottom: 0;
  }
}
.result-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}
.rank-wrap {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary-second);
  background: color-mix(in srgb, var(--color-primary-second) 8%, transparent);
  display: grid;
  place-items: center;
  width: 32px;
  height: 36px;
  border-radius: 6px;
  flex-shrink: 0;
}
.result-name {
  flex: 1;
  min-width: 0;
  strong {
    color: var(--font-main-color);
    font-size: 13px;
    font-weight: 500;
  }
  > div {
    color: var(--font-info-color);
    font-size: 11px;
    margin-top: 4px;
  }
}
.result-text {
  overflow-wrap: anywhere;
  font-size: 13px;
  margin: 16px 0 0;
  color: var(--font-text-color);
  :deep(img) {
    width: auto;
    max-width: 100%;
    max-height: 220px;
    object-fit: contain;
  }
  ul {
    display: block;
    list-style-type: disc;
    margin-block-start: 0;
    margin-block-end: 0;
    padding-inline-start: 20px;
    unicode-bidi: isolate;
  }
}
.concept-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-main-color);
  font-size: 11px;
  color: var(--font-info-color);
}
.concept-tag {
  cursor: pointer;
  margin: 0;
  font-size: 11px;
  .anticon {
    margin-left: 6px;
  }
  &:hover {
    color: var(--color-primary-second);
    border-color: var(--color-primary-second);
  }
}
.media-wrap {
  margin-top: 16px;
  :deep(.intel-image-img) {
    width: auto;
    max-width: 100%;
    max-height: 220px;
    object-fit: contain;
  }
  video,
  audio {
    max-width: 100%;
  }
}
.notice-wrap {
  margin-bottom: 16px;
}
</style>
