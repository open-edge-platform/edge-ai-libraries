<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div v-if="libraryData" class="chat-container">
    <section class="conversation-wrap" :class="{ 'is-empty': !messages.length }">
      <div class="conversation-header">
        <div class="conversation-title">
          <div class="chat-icon"><RobotOutlined /></div>
          <div>
            <h3>{{ $t("console.knowledgeAssistant") }}</h3>
            <div class="scope-tags">
              <DatabaseOutlined />
              {{ libraryData.name }}
              <span v-if="configRef?.form.model">
                · {{ configRef.form.model }}
              </span>
            </div>
          </div>
        </div>
        <a-space>
          <a-tooltip :title="$t('console.clear')">
            <a-button
              type="text"
              :aria-label="$t('console.clear')"
              @click="handleClear"
            >
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-tooltip>
          <a-button type="primary" @click="handleConfigOpen">
            <template #icon><SettingOutlined /></template>
            {{ $t("console.configuration") }}
          </a-button>
        </a-space>
      </div>
      <div class="chat-log-wrap">
        <div
          ref="chatLog"
          class="chat-log"
          aria-live="polite"
          @scroll="handleChatScroll"
        >
          <div v-if="!messages.length" class="welcome-wrap">
            <div class="welcome-icon"><RobotOutlined /></div>
            <h2>{{ $t("console.chatWelcome") }}</h2>
            <p>{{ $t("console.chatWelcomeHint") }}</p>
            <a-button
              v-if="!canSend"
              class="mt-12"
              type="primary"
              ghost
              @click="handleConfigOpen"
            >
              {{ $t("console.configureEndpoint") }}
              <ArrowRightOutlined />
            </a-button>
          </div>
          <MessageItem
            v-for="(message, index) in messages"
            :key="index"
            :message="message"
            @citation="handleCitation"
          />
        </div>
        <a-button
          v-if="showScrollToBottom"
          class="scroll-to-bottom"
          shape="circle"
          :aria-label="$t('console.scrollToBottom')"
          @click="scrollToBottom"
        >
          <template #icon><ArrowDownOutlined /></template>
        </a-button>
      </div>
      <div class="composer-wrap">
        <div class="composer-input">
          <a-textarea
            v-model:value="question"
            :bordered="false"
            :auto-size="{ minRows: 2, maxRows: 6 }"
            :placeholder="$t('console.chatPlaceholder')"
            @keydown="handleKeydown"
          />
          <div class="composer-actions">
            <span>
              <SafetyCertificateOutlined />
              {{ $t("console.groundedAnswers") }}
            </span>
            <a-button v-if="sending" danger @click="handleStop">
              <template #icon><StopOutlined /></template>
              {{ $t("console.stop") }}
            </a-button>
            <a-button
              v-else
              type="primary"
              :disabled="!question.trim() || !canSend"
              @click="handleSend"
            >
              <template #icon><SendOutlined /></template>
              {{ $t("console.send") }}
            </a-button>
          </div>
        </div>
        <p>{{ $t("console.chatEndpointHint") }}</p>
      </div>
    </section>
    <section v-if="result" class="evidence-wrap">
      <div class="evidence-heading">
        <FileSearchOutlined />
        <strong>{{ $t("console.retrievalEvidence") }}</strong>
        <a-tag>{{ result.chunks.length }}</a-tag>
      </div>
      <a-tabs v-model:activeKey="evidenceTab">
        <a-tab-pane key="results" :tab="$t('console.citations')">
          <Results
            :result="result"
            :excluded-ids="configRef?.excludedIds"
            @exclude="handleExclude"
            @focus="handleFocus"
          />
        </a-tab-pane>
        <a-tab-pane key="graph" :tab="$t('console.graph')" force-render>
          <ConceptGraph
            :library-data="libraryData"
            :result="result"
            :focus="focus"
          />
        </a-tab-pane>
      </a-tabs>
    </section>
    <ConfigDrawer
      ref="configRef"
      :open="configOpen"
      :library-data="libraryData"
      @close="handleConfigClose"
    />
    <a-modal
      v-model:open="citationOpen"
      :title="$t('console.citations')"
      :footer="null"
      width="640px"
    >
      <div v-if="citation" class="citation-body">
        <div class="citation-title">
          <FileTextOutlined />
          <strong>
            {{
              citation.metadata.file_name ||
              citation.metadata.library ||
              citation.id
            }}
          </strong>
          <span v-if="citation.metadata.page != null">
            p.{{ citation.metadata.page }}
          </span>
        </div>
        <p>{{ citation.text }}</p>
      </div>
    </a-modal>
  </div>
</template>
<script lang="ts" setup name="ConsoleChat">
import { computed, nextTick, onUnmounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { isCancel } from "axios";
import {
  ArrowDownOutlined,
  ArrowRightOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  SettingOutlined,
  StopOutlined,
} from "@ant-design/icons-vue";
import type { Chunk, RetrieveResult } from "@/api/console/type";
import type { ConsolePageProps } from "../../types/console";
import type { ConceptFocus } from "../retrieve/Type";
import Results from "../retrieve/components/Results.vue";
import ConceptGraph from "../retrieve/components/ConceptGraph.vue";
import ConfigDrawer from "./components/ConfigDrawer.vue";
import MessageItem from "./components/MessageItem.vue";
import { buildMessages, readCompletion, stripThinking } from "./SseService";
import type { ChatMessage } from "./Type";
defineProps<ConsolePageProps>();
const { t } = useI18n();
const configRef = ref<InstanceType<typeof ConfigDrawer>>();
const configOpen = ref(false);
const handleConfigOpen = () => {
  configOpen.value = true;
};
const handleConfigClose = () => {
  configOpen.value = false;
};
const handleExclude = (id: string) => configRef.value?.excludeChunk(id);
const handleStop = () => controller?.abort();
const chatLog = ref<HTMLElement>();
const showScrollToBottom = ref(false);
const shouldFollowMessages = ref(true);
const question = ref("");
const messages = ref<ChatMessage[]>([]);
const sending = ref(false);
const result = ref<RetrieveResult>();
const focus = ref<ConceptFocus>();
const evidenceTab = ref("results");
const citation = ref<Chunk>();
const citationOpen = ref(false);
const canSend = computed(
  () =>
    !!configRef.value?.form.endpoint.trim() &&
    !!configRef.value?.form.model.trim(),
);
let controller: AbortController | undefined;
const handleSend = async () => {
  if (sending.value || !question.value.trim() || !canSend.value) return;
  const input = question.value.trim();
  const history = messages.value.slice();
  const answer = reactive<ChatMessage>({
    role: "assistant",
    content: "",
    pending: "retrieving",
  });
  controller = new AbortController();
  const signal = controller.signal;
  sending.value = true;
  question.value = "";
  messages.value.push({ role: "user", content: input }, answer);
  try {
    const data = await configRef.value!.retrieve(input, signal);
    signal.throwIfAborted();
    result.value = data;
    focus.value = undefined;
    if (data.graph_traces?.length) evidenceTab.value = "graph";
    answer.sources = data.chunks;
    answer.pending = "answering";
    const form = configRef.value!.form;
    const base = form.endpoint
      .trim()
      .replace(/\/+$/, "")
      .replace(/\/chat\/completions$/, "");
    const url = new URL(base);
    if (!["http:", "https:"].includes(url.protocol))
      throw new Error(t("console.invalidUrl"));
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (form.apiKey.trim())
      headers.Authorization = `Bearer ${form.apiKey.trim()}`;
    const response = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers,
      signal,
      body: JSON.stringify({
        model: form.model.trim(),
        messages: buildMessages(input, data.chunks, history),
        stream: true,
      }),
    });
    await readCompletion(
      response,
      (content) => {
        answer.content += content;
        answer.pending = undefined;
      },
      () => {
        answer.pending = "thinking";
      },
    );
    if (!stripThinking(answer.content).trim())
      throw new Error(t("console.emptyAnswer"));
  } catch (error) {
    if (signal.aborted || isCancel(error)) answer.error = t("console.stopped");
    else if (error instanceof TypeError)
      answer.error = t("console.chatNetworkError");
    else answer.error = error instanceof Error ? error.message : String(error);
  } finally {
    answer.pending = undefined;
    sending.value = false;
    controller = undefined;
  }
};
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    handleSend();
  }
};
const handleClear = () => {
  controller?.abort();
  messages.value = [];
  result.value = undefined;
  shouldFollowMessages.value = true;
  showScrollToBottom.value = false;
};
const handleChatScroll = () => {
  const element = chatLog.value;
  if (!element) return;
  shouldFollowMessages.value =
    element.scrollHeight - element.scrollTop - element.clientHeight <= 80;
  showScrollToBottom.value = !shouldFollowMessages.value;
};
const scrollToBottom = async () => {
  shouldFollowMessages.value = true;
  showScrollToBottom.value = false;
  await nextTick();
  chatLog.value?.scrollTo({
    top: chatLog.value.scrollHeight,
    behavior: "smooth",
  });
};
const handleCitation = (chunk: Chunk) => {
  citation.value = chunk;
  citationOpen.value = true;
};
const handleFocus = (value: ConceptFocus) => {
  focus.value = value;
  evidenceTab.value = "graph";
};
watch(
  () => messages.value.map((message) => [message.content, message.pending]),
  async () => {
    await nextTick();
    if (shouldFollowMessages.value && chatLog.value)
      chatLog.value.scrollTop = chatLog.value.scrollHeight;
  },
);
onUnmounted(() => controller?.abort());
</script>
<style scoped lang="less">
.chat-container {
  display: flex;
  gap: 20px;
  align-items: stretch;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.conversation-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-main-color);
  border-radius: 10px;
  background: var(--bg-content-color);
  overflow: hidden;
}
.conversation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-main-color);
  flex-wrap: wrap;
  flex-shrink: 0;
}
.conversation-title {
  display: flex;
  gap: 12px;
  align-items: center;
  h3 {
    margin: 0 0 5px;
    font-size: 15px;
    color: var(--font-main-color);
  }
}
.chat-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--bg-blue-color);
  color: var(--color-white);
  font-size: 23px;
}
.scope-tags {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 11px;
  color: var(--font-info-color);
}
.chat-log {
  overflow-y: auto;
  padding: 26px;
  height: 100%;
}
.chat-log-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
}
.scroll-to-bottom {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  box-shadow: 0 2px 8px var(--bg-primary-shadow);
}
.welcome-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  text-align: center;
  padding: 12px;
  h2 {
    font-size: 24px;
    font-weight: 500;
    color: var(--font-main-color);
    margin: 18px 0 10px;
  }
  > p {
    font-size: 13px;
    color: var(--font-info-color);
    max-width: 460px;
    line-height: 1.8;
  }
}
.welcome-icon {
  width: 68px;
  height: 68px;
  display: grid;
  place-items: center;
  border-radius: 20px;
  background: var(--bg-blue-color);
  color: var(--color-white);
  font-size: 38px;
  box-shadow: 0 6px 24px var(--bg-primary-shadow);
}
.suggestion-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin: 26px 0 22px;
  button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 14px;
    background: var(--bg-card-color);
    border: 1px solid var(--border-main-color);
    border-radius: 8px;
    cursor: pointer;
    color: var(--font-text-color);
    font-size: 12px;
    &:hover {
      border-color: var(--color-primary-second);
      color: var(--color-primary-second);
    }
    > .anticon:first-child {
      color: var(--color-primary-second);
    }
  }
}
.composer-wrap {
  flex-shrink: 0;
  padding: 16px 24px;
  > p {
    margin: 10px 0 0;
    font-size: 11px;
    color: var(--font-tip-color);
    text-align: center;
  }
}
.conversation-wrap.is-empty {
  overflow-y: auto;
  .chat-log-wrap {
    flex: none;
    margin-top: auto;
  }
  .chat-log {
    height: auto;
    overflow: visible;
  }
  .welcome-wrap {
    height: auto;
  }
  .composer-wrap {
    margin-bottom: auto;
  }
}
.composer-input {
  border: 1px solid var(--border-main-color);
  border-radius: 10px;
  background: var(--bg-card-color);
  &:focus-within {
    border-color: var(--color-primary-second);
  }
  :deep(textarea) {
    background: transparent;
    padding: 14px 16px 8px;
    resize: none;
    box-shadow: none;
  }
}
.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 12px;
  > span {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 11px;
    color: var(--font-info-color);
  }
}
.evidence-wrap {
  width: 380px;
  flex-shrink: 0;
  border: 1px solid var(--border-main-color);
  border-radius: 10px;
  background: var(--bg-content-color);
  overflow-y: auto;
  :deep(.intel-tabs-nav) {
    padding: 0 18px;
  }
  :deep(.intel-tabs-content-holder) {
    padding: 0 16px 16px;
  }
}
.evidence-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 18px 4px;
  > .anticon {
    color: var(--color-primary-second);
  }
  strong {
    flex: 1;
    font-size: 14px;
    font-weight: 500;
    color: var(--font-main-color);
  }
}
.citation-body {
  padding: 16px 0;
  > p {
    white-space: pre-wrap;
    line-height: 1.9;
    margin: 18px 0;
  }
}
.citation-title {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--font-main-color);
  .anticon {
    color: var(--color-primary-second);
  }
  > span:last-child {
    color: var(--font-info-color);
    font-size: 12px;
  }
}
@media (max-width: 1200px) {
  .chat-container {
    flex-direction: column;
  }
  .conversation-wrap {
    min-height: 0;
  }
  .evidence-wrap {
    width: auto;
    flex: 0 1 40%;
    min-height: 0;
  }
}
@media (max-width: 700px) {
  .conversation-header,
  .composer-wrap {
    padding: 14px;
  }
  .chat-log {
    padding: 16px;
  }
}
</style>
