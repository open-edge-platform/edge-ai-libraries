<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="message-container" :class="message.role">
    <div v-if="message.role === 'assistant'" class="avatar-wrap">
      <RobotOutlined />
    </div>
    <div class="message-body">
      <div class="message-author">
        <template v-if="message.role === 'assistant'">
          {{ $t("console.assistant") }}
        </template>
        <template v-else>{{ $t("console.user") }}</template>
      </div>
      <div class="message-content intel-markdown" @click="handleImageClick">
        <template v-for="(part, index) in contentParts" :key="index">
          <a-tooltip
            v-if="part.source"
            :title="part.source.metadata.file_name || part.source.id"
          >
            <button
              class="citation-button"
              @click="handleCitation(part.source)"
            >
              {{ part.number }}
              <FileTextOutlined />
            </button>
          </a-tooltip>
          <div
            v-else-if="message.role === 'assistant'"
            class="message-markdown"
            v-html="renderMarkdown(part.text)"
          ></div>
          <span v-else>{{ part.text }}</span>
        </template>
      </div>
      <a-image
        v-if="message.role === 'assistant'"
        :style="{ display: 'none' }"
        :src="imageSrc"
        :preview="{
          visible: imageVisible,
          onVisibleChange: handleImageVisible,
        }"
      />
      <div v-if="message.pending" class="pending-wrap">
        <LoadingOutlined />
        <span v-if="message.pending === 'retrieving'">
          {{ $t("console.retrieving") }}
        </span>
        <span v-else-if="message.pending === 'thinking'">
          {{ $t("console.thinking") }}
        </span>
        <span v-else>{{ $t("console.answering") }}</span>
      </div>
      <a-alert
        v-if="message.error"
        type="error"
        showIcon
        :message="message.error"
        class="error-wrap"
      />
      <div
        v-if="
          message.role === 'assistant' && message.content && !message.pending
        "
        class="message-footer"
      >
        <a-tooltip :title="$t('common.copy')">
          <a-button
            type="text"
            size="small"
            :aria-label="$t('common.copy')"
            @click="handleCopy"
          >
            <template #icon><CopyOutlined /></template>
          </a-button>
        </a-tooltip>
        <span v-if="message.sources">
          {{ $t("console.citations") }} · {{ message.sources.length }}
        </span>
      </div>
    </div>
    <a-avatar v-if="message.role === 'user'" size="small" class="user-avatar">
      <UserOutlined />
    </a-avatar>
  </div>
</template>
<script lang="ts" setup name="MessageItem">
import { computed, ref } from "vue";
import { marked } from "marked";
import {
  CopyOutlined,
  FileTextOutlined,
  LoadingOutlined,
  RobotOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import { useClipboard } from "@/utils/clipboard";
import type { Chunk } from "@/api/console/type";
import type { ChatMessage } from "../Type";
import { stripThinking } from "../SseService";
import CustomRenderer from "@/utils/customRenderer";
const props = defineProps<{ message: ChatMessage }>();
const emit = defineEmits<{ citation: [chunk: Chunk] }>();
const handleCitation = (chunk: Chunk) => emit("citation", chunk);
const { copy } = useClipboard();
const imageSrc = ref("");
const imageVisible = ref(false);
const handleImageVisible = (visible: boolean) => (imageVisible.value = visible);
const handleImageClick = (event: MouseEvent) => {
  if (
    props.message.role !== "assistant" ||
    !(event.target instanceof HTMLImageElement)
  )
    return;
  imageSrc.value = event.target.src;
  imageVisible.value = true;
};
const renderMarkdown = (text: string) =>
  marked.parse(text, { renderer: CustomRenderer, async: false });
const contentParts = computed(() => {
  if (props.message.role === "user")
    return [{ text: props.message.content, number: 0, source: undefined }];
  return stripThinking(props.message.content)
    .split(/(\[\d+\])/)
    .map((text) => {
      const number = /^\[\d+\]$/.test(text) ? Number(text.slice(1, -1)) : 0;
      return {
        text,
        number,
        source: number ? props.message.sources?.[number - 1] : undefined,
      };
    });
});
const handleCopy = () => copy(stripThinking(props.message.content));
</script>
<style scoped lang="less">
.message-container {
  display: flex;
  gap: 12px;
  margin-bottom: 28px;
  &.user {
    justify-content: flex-end;
    .message-body {
      flex: none;
      max-width: 80%;
    }
    .message-author {
      text-align: right;
    }
    .message-content {
      padding: 12px 16px;
      white-space: pre-wrap;
      background: color-mix(
        in srgb,
        var(--color-primary-second) 10%,
        var(--bg-content-color)
      );
      border-radius: 10px 2px 10px 10px;
    }
  }
}
.avatar-wrap {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: var(--bg-blue-color);
  color: var(--color-white);
  font-size: 22px;
  flex-shrink: 0;
}
.user-avatar {
  background: var(--bg-card-color);
  color: var(--font-text-color);
  flex-shrink: 0;
}
.message-body {
  flex: 1;
  min-width: 0;
}
.message-author {
  font-size: 11px;
  color: var(--font-info-color);
  margin: 0 0 8px;
}
.message-content {
  overflow-wrap: anywhere;
  color: var(--font-main-color);
  font-size: 14px;
  line-height: 1.9;
}
.message-markdown {
  :deep(p:first-child) {
    margin-top: 0;
  }
  :deep(p:last-child) {
    margin-bottom: 0;
  }
}
.citation-button {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  border: 0;
  padding: 1px 5px;
  margin: 0 3px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--color-primary-second) 10%, transparent);
  color: var(--color-primary-second);
  font-size: 11px;
  cursor: pointer;
}
.pending-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--font-info-color);
  margin: 8px 0;
}
.message-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 6px 0 0;
  color: var(--font-info-color);
  font-size: 11px;
}
.error-wrap {
  margin-top: 12px;
}
</style>
