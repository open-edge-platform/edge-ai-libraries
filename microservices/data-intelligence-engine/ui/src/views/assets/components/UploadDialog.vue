<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-modal
    v-model:open="modelVisible"
    :title="$t('console.upload')"
    width="780px"
    centered
    :maskClosable="false"
    :closable="!submitLoading"
    wrap-class-name="upload-assets-modal"
    @cancel="handleClose"
  >
    <div class="upload-dialog">
      <a-alert
        type="info"
        showIcon
        :message="$t('console.uploadHint')"
        class="notice-wrap"
      />
      <a-tabs v-model:activeKey="activeKey">
        <a-tab-pane key="files">
          <template #tab>
            <UploadOutlined />
            {{ $t("console.localFiles") }}
          </template>
          <div class="upload-zone" @dragover.prevent @drop.prevent="handleDrop">
            <a-upload-dragger
              :before-upload="handleBeforeUpload"
              :showUploadList="false"
              multiple
              :disabled="submitLoading || stagingFiles"
              :openFileDialogOnClick="false"
            >
              <InboxOutlined class="upload-icon" />
              <p class="upload-title">{{ $t("console.dropFiles") }}</p>
              <p class="upload-hint">{{ $t("console.fileSupportHint") }}</p>
              <p class="upload-hint upload-formats">
                {{ $t("console.documentFormatsHint") }}
              </p>
              <a-space>
                <a-upload
                  :before-upload="handleBeforeUpload"
                  :showUploadList="false"
                  multiple
                  :disabled="submitLoading || stagingFiles"
                >
                  <a-button :disabled="submitLoading || stagingFiles">
                    {{ $t("console.chooseFiles") }}
                  </a-button>
                </a-upload>
                <a-upload
                  :before-upload="handleBeforeUpload"
                  :showUploadList="false"
                  directory
                  multiple
                  :disabled="submitLoading || stagingFiles"
                >
                  <a-button :disabled="submitLoading || stagingFiles">
                    {{ $t("console.chooseFolder") }}
                  </a-button>
                </a-upload>
              </a-space>
            </a-upload-dragger>
          </div>
          <div v-if="fileList.length" class="file-list">
            <div class="list-title">
              {{ $t("console.selectedFiles", { count: fileList.length }) }}
              <a-button
                type="link"
                size="small"
                :disabled="submitLoading || stagingFiles"
                @click="handleClearFiles"
              >
                {{ $t("common.clear") }}
              </a-button>
            </div>
            <div
              v-for="(item, index) in fileList"
              :key="item.path"
              class="file-item"
            >
              <FileTextOutlined />
              <div class="file-content">
                <span>{{ item.path }}</span>
                <a-progress
                  v-if="submitLoading || item.progress"
                  :percent="item.progress"
                  :status="item.failed ? 'exception' : undefined"
                  size="small"
                />
              </div>
              <span class="file-size">
                {{ (item.file.size / 1024).toFixed(1) }} KB
              </span>
              <a-button
                type="text"
                size="small"
                :disabled="submitLoading"
                :aria-label="$t('common.delete')"
                @click="handleRemoveFile(index)"
              >
                <CloseOutlined />
              </a-button>
            </div>
          </div>
        </a-tab-pane>
        <a-tab-pane key="text">
          <template #tab>
            <AlignLeftOutlined />
            {{ $t("console.text") }}
          </template>
          <a-textarea
            v-model:value="form.text"
            :rows="9"
            :disabled="submitLoading"
            :placeholder="$t('console.textPlaceholder')"
          />
        </a-tab-pane>
        <a-tab-pane key="paths">
          <template #tab>
            <FolderOpenOutlined />
            {{ $t("console.serverPaths") }}
          </template>
          <a-textarea
            v-model:value="form.paths"
            :rows="6"
            :disabled="submitLoading"
            placeholder="/data/document.pdf, /data/knowledge"
          />
          <p class="field-hint">{{ $t("console.serverPathsHint") }}</p>
        </a-tab-pane>
      </a-tabs>
      <a-form layout="vertical" class="pool-form">
        <a-form-item :label="$t('console.pools')">
          <a-select
            v-model:value="form.poolIds"
            mode="multiple"
            :disabled="submitLoading"
            :placeholder="$t('console.pleaseSelect')"
            :options="
              libraryData.asset_pools.map((pool) => ({
                value: pool.id,
                label: pool.name,
              }))
            "
          />
          <p class="field-hint">{{ $t("console.ingestHint") }}</p>
        </a-form-item>
      </a-form>
      <a-alert
        v-if="validationError"
        type="error"
        showIcon
        :message="validationError"
      />
    </div>
    <template #footer>
      <a-button :disabled="submitLoading" @click="handleClose">
        {{ $t("common.cancel") }}
      </a-button>
      <a-button
        type="primary"
        :loading="submitLoading || stagingFiles"
        @click="handleSubmit"
      >
        {{ $t("console.addAssets") }}
      </a-button>
    </template>
  </a-modal>
</template>
<script lang="ts" setup name="UploadDialog">
import { reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import JSZip from "jszip";
import {
  AlignLeftOutlined,
  CloseOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  UploadOutlined,
} from "@ant-design/icons-vue";
import { requestAssetCreate, requestAssetUpload } from "@/api/console";
import type { IngestResult, Library, UploadResult } from "@/api/console/type";
import { customNotification } from "@/utils/notification";
import { readDroppedFiles } from "../AssetUtils";
import type { StagedFile } from "../AssetUtils";
const props = defineProps<{
  libraryData: Library;
  poolId?: string;
  files?: StagedFile[];
}>();
const emit = defineEmits<{ close: []; created: [result: IngestResult] }>();
const handleClose = () => emit("close");
const handleClearFiles = () => {
  fileList.value = [];
};
const handleRemoveFile = (index: number) => {
  fileList.value.splice(index, 1);
};
const { t } = useI18n();
const modelVisible = ref(true);
const activeKey = ref("files");
const submitLoading = ref(false);
const stagingFiles = ref(false);
let pendingStages = 0;
const validationError = ref("");
const fileList = ref<
  (StagedFile & { progress: number; failed: boolean; result?: UploadResult })[]
>([]);
const form = reactive({
  text: "",
  paths: "",
  poolIds: props.poolId ? [props.poolId] : [],
});
const handleStageFiles = async (files: StagedFile[]) => {
  pendingStages++;
  stagingFiles.value = true;
  try {
    for (const item of files) {
      if (item.path.split("/").some((part) => part.startsWith("."))) continue;
      if (!/\.zip$/i.test(item.path)) {
        if (!fileList.value.some((current) => current.path === item.path))
          fileList.value.push({ ...item, progress: 0, failed: false });
        continue;
      }
      try {
        const zip = await JSZip.loadAsync(item.file);
        const entries = Object.values(zip.files).filter(
          (entry) =>
            !entry.dir &&
            !entry.name.split("/").some((part) => part.startsWith(".")),
        );
        if (!entries.length) {
          validationError.value = t("console.emptyZip");
          continue;
        }
        const root = item.path.slice(0, -4);
        for (const entry of entries) {
          const path = `${root}/${entry.name}`;
          if (fileList.value.some((current) => current.path === path)) continue;
          const blob = await entry.async("blob");
          const name = entry.name.split("/").pop()!;
          fileList.value.push({
            file: new File([blob], name, {
              type: blob.type || "application/octet-stream",
            }),
            path,
            progress: 0,
            failed: false,
          });
        }
      } catch (error) {
        customNotification(
          "error",
          t("common.error"),
          error instanceof Error ? error.message : String(error),
        );
      }
    }
  } finally {
    if (--pendingStages === 0) stagingFiles.value = false;
  }
};
if (props.files) void handleStageFiles(props.files);
const handleBeforeUpload = (file: File) => {
  void handleStageFiles([{ file, path: file.webkitRelativePath || file.name }]);
  return false;
};
const handleDrop = async (event: DragEvent) => {
  if (submitLoading.value || stagingFiles.value || !event.dataTransfer) return;
  try {
    handleStageFiles(await readDroppedFiles(event.dataTransfer));
  } catch (error) {
    customNotification(
      "error",
      t("common.error"),
      error instanceof Error ? error.message : String(error),
    );
  }
};
const handleSubmit = async () => {
  if (stagingFiles.value) return;
  validationError.value = "";
  const paths = form.paths
    .split(",")
    .map((path) => path.trim())
    .filter(Boolean);
  if (!fileList.value.length && !paths.length && !form.text.trim()) {
    validationError.value = t("console.ingestRequired");
    return;
  }
  submitLoading.value = true;
  try {
    let next = 0;
    const uploadFiles = async () => {
      while (next < fileList.value.length) {
        const item = fileList.value[next++];
        if (item.result) continue;
        item.failed = false;
        try {
          item.result = await requestAssetUpload(
            props.libraryData.name,
            item.path,
            item.file,
            (event) => {
              if (event.total)
                item.progress = Math.round((event.loaded / event.total) * 100);
            },
          );
        } catch (error) {
          item.failed = true;
          throw error;
        }
      }
    };
    const uploads = await Promise.allSettled([
      uploadFiles(),
      uploadFiles(),
      uploadFiles(),
    ]);
    const failed = uploads.find((item) => item.status === "rejected");
    if (failed?.status === "rejected") throw failed.reason;
    const folders = new Map<string, boolean>();
    const skipped: string[] = [];
    for (const item of fileList.value) {
      const result = item.result!;
      const slash = item.path.indexOf("/");
      if (slash < 0)
        (result.supported ? paths : skipped).push(
          result.supported ? result.name : item.path,
        );
      else {
        const root =
          result.name.slice(0, result.name.length - item.path.length) +
          item.path.slice(0, slash);
        folders.set(root, Boolean(folders.get(root) || result.supported));
      }
    }
    for (const [name, supported] of folders)
      (supported ? paths : skipped).push(name);
    if (!paths.length && !form.text.trim()) {
      validationError.value = skipped.length
        ? t("console.unsupportedUploads", { names: skipped.join(", ") })
        : t("console.ingestRequired");
      return;
    }
    if (skipped.length)
      customNotification(
        "warning",
        t("console.upload"),
        t("console.skipped", { names: skipped.join(", ") }),
      );
    const data = await requestAssetCreate(props.libraryData.name, {
      asset_pool_ids: form.poolIds,
      file_paths: paths,
      text: form.text.trim() || null,
    });
    customNotification(
      "success",
      t("common.success"),
      t("console.accepted", { count: data.asset_ids.length }),
    );
    emit("created", data);
    emit("close");
  } finally {
    submitLoading.value = false;
  }
};
</script>
<style scoped lang="less">
:global(.upload-assets-modal .intel-modal-content) {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 32px);
  max-height: calc(100dvh - 32px);
}
:global(.upload-assets-modal .intel-modal-body) {
  min-height: 0;
  overflow-y: auto;
}
:global(.upload-assets-modal .intel-modal-header),
:global(.upload-assets-modal .intel-modal-footer) {
  flex-shrink: 0;
}
.upload-dialog {
  padding: 16px 0 4px;
}
.notice-wrap {
  margin-bottom: 12px;
}
.upload-zone {
  :deep(.intel-upload-drag) {
    padding: 20px 12px;
    background: var(--bg-card-color);
    border-color: var(--border-info);
    border-radius: 8px;
  }
  .upload-icon {
    font-size: 42px;
    color: var(--color-primary-second);
  }
  .upload-title {
    font-size: 16px;
    color: var(--font-main-color);
    margin: 12px 0 6px;
  }
  .upload-hint {
    color: var(--font-info-color);
    font-size: 12px;
    margin-bottom: 4px;
  }
  .upload-formats {
    margin-bottom: 20px;
    overflow-wrap: anywhere;
  }
}
.file-list {
  margin-top: 16px;
  max-height: 220px;
  overflow-y: auto;
}
.list-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--font-info-color);
  font-size: 12px;
  margin-bottom: 8px;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid var(--border-main-color);
  > .anticon {
    color: var(--color-primary-second);
  }
}
.file-content {
  flex: 1;
  min-width: 0;
  span {
    display: block;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-size: 13px;
  }
}
.file-size,
.field-hint {
  color: var(--font-info-color);
  font-size: 12px;
}
.field-hint {
  margin-top: 8px;
  line-height: 1.7;
}
.pool-form {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-main-color);
}
</style>
