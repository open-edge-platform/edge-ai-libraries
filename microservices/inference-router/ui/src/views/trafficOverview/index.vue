<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->
<template>
  <section
    class="traffic-page router-detail-module"
    role="tabpanel"
    :aria-label="t('router.routerTrafficTitle')"
  >
    <header class="router-module-heading">
      <span class="section-icon"><DeploymentUnitOutlined /></span>
      <div class="traffic-title">
        <div class="section-title">{{ t("router.routerTrafficTitle") }}</div>
        <div class="section-caption">
          {{ t("router.routerTrafficCaption") }}
        </div>
      </div>
      <div class="router-module-actions heading-actions">
        <a-checkbox v-model:checked="autoRefresh">{{
          t("router.traffic.autoRefresh")
        }}</a-checkbox>
        <a-button
          type="text"
          shape="circle"
          :loading="loading"
          :title="t('router.refresh')"
          :aria-label="t('router.refresh')"
          @click="loadTraffic"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </header>

    <div v-if="error" class="traffic-state error-state" role="alert">
      <ExclamationCircleOutlined />
      <span>{{ t("router.traffic.error") }}</span>
      <a-button :loading="loading" @click="loadTraffic">{{
        t("common.retry")
      }}</a-button>
    </div>
    <div v-else-if="loading && !snapshot" class="traffic-state" role="status">
      <a-spin /> <span>{{ t("router.traffic.loading") }}</span>
    </div>
    <template v-else-if="snapshot">
      <div class="traffic-controls">
        <div class="traffic-meta">
          <ClockCircleOutlined />
          <time :datetime="snapshot.collected_at">
            {{ t("router.traffic.updated") }} · {{ collectedAt }}
          </time>
        </div>
        <a-radio-group
          v-model:value="mode"
          class="traffic-mode-switch"
          button-style="solid"
          :aria-label="t('router.traffic.topology')"
        >
          <a-radio-button value="requests">
            <BranchesOutlined /> {{ t("router.traffic.requests") }}
          </a-radio-button>
          <a-radio-button value="tokens">
            <DatabaseOutlined /> {{ t("router.traffic.tokens") }}
          </a-radio-button>
        </a-radio-group>
      </div>
      <RequestTraffic v-if="mode === 'requests'" :snapshot="snapshot" />
      <TokenTraffic v-else :snapshot="snapshot" />
    </template>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
} from "vue";
import { useI18n } from "vue-i18n";
import {
  BranchesOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import { getRouterTraffic } from "@/api/trafficOverview";
import { formatRouterTraffic } from "./type";
import type { TrafficMode } from "./type";
import { RequestTraffic, TokenTraffic } from "./components";

const { t, locale } = useI18n();
const traffic = shallowRef<unknown>();
const mode = ref<TrafficMode>("tokens");
const autoRefresh = ref(false);
const loading = ref(false);
const error = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;
const collectedAtTimestamp = ref("");
const snapshot = computed(() =>
  traffic.value
    ? {
        ...formatRouterTraffic(traffic.value, mode.value),
        collected_at: collectedAtTimestamp.value,
      }
    : undefined,
);
const collectedAt = computed(() =>
  snapshot.value
    ? new Date(snapshot.value.collected_at).toLocaleString(
        locale.value.replace("_", "-"),
      )
    : "",
);

async function loadTraffic() {
  loading.value = true;
  error.value = false;
  try {
    traffic.value = await getRouterTraffic();
    collectedAtTimestamp.value = new Date().toISOString();
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

watch(autoRefresh, (enabled) => {
  if (timer) clearInterval(timer);
  timer = enabled
    ? setInterval(() => {
        if (!document.hidden) void loadTraffic();
      }, 5000)
    : undefined;
});
onMounted(() => {
  void loadTraffic();
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped lang="less">
.traffic-page {
  min-width: 0;
  color: var(--font-main-color);
}
.heading-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.traffic-title {
  min-width: 0;
}

.traffic-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 4px 0 8px;
}
.traffic-meta {
  color: var(--font-tip-color);
  font-size: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px;
}
.traffic-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.traffic-mode-switch {
  flex: 0 0 auto;
}
.traffic-state {
  min-height: 360px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: center;
  justify-content: center;
  color: var(--font-tip-color);
}
.error-state > .anticon {
  color: var(--color-error);
  font-size: 28px;
}
@media (max-width: 600px) {
  .router-module-heading {
    flex-wrap: wrap;
  }
  .traffic-controls {
    flex-wrap: wrap;
  }
}
</style>
