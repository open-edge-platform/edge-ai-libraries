<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div class="router-monitor">
    <section class="router-detail-page" :aria-label="t('router.routerTitle')">
      <div
        class="router-detail-body"
        :class="{ 'collapsed-menu': isMenuCollapsed }"
      >
        <aside
          class="router-detail-tabs"
          :class="{ collapsed: isMenuCollapsed }"
          role="navigation"
          :aria-label="t('router.routerDetailTabsLabel')"
        >
          <div class="router-tabs-heading">
            <div class="router-tabs-heading-copy">
              <span>{{ t("router.routerTab") }}</span>
              <small>{{ t("router.routerDetailTabsLabel") }}</small>
            </div>
            <button
              class="router-tabs-toggle"
              type="button"
              :title="isMenuCollapsed ? t('router.pin') : t('router.close')"
              @click="toggleMenuCollapsed"
            >
              <component
                :is="isMenuCollapsed ? MenuUnfoldOutlined : MenuFoldOutlined"
              />
            </button>
          </div>

          <RouterLink
            v-for="detailRoute in routerDetailRoutes"
            :key="detailRoute.name"
            :to="{ name: detailRoute.name }"
            class="router-detail-tab"
            :class="{ active: route.name === detailRoute.name }"
            :aria-current="route.name === detailRoute.name ? 'page' : undefined"
            :title="isMenuCollapsed ? detailRoute.label : ''"
          >
            <span class="router-tab-icon">
              <component :is="detailRoute.icon" />
            </span>
            <span class="router-tab-main">
              <span class="router-tab-label">{{ detailRoute.label }}</span>
            </span>
          </RouterLink>

          <div class="router-side-summary">
            <div class="router-side-status">
              <span
                class="router-status-dot"
                :class="routerHealthStatusTone"
              ></span>
              <span>{{ t("router.routerRuntimeStatus") }}</span>
              <strong>{{ routerHealthStatusText }}</strong>
            </div>
          </div>
        </aside>

        <main class="router-detail-route-panel">
          <RouterView />
        </main>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Component } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import {
  AppstoreOutlined,
  BranchesOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FileProtectOutlined,
  FundOutlined,
  DeploymentUnitOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from "@ant-design/icons-vue";
import { getRouterHealth } from "@/api/overview";

type RouterPageRouteName =
  | "Overview"
  | "TokenOverview"
  | "LatencyOverview"
  | "ProviderConfig"
  | "PromptConfig"
  | "PluginsConfig"
  | "PolicyConfig"
  | "StrategyConfig"
  | "RouterTraffic";

interface RouterDetailRoute {
  name: RouterPageRouteName;
  label: string;
  icon: Component;
}

const { t } = useI18n();
const route = useRoute();
const isMenuCollapsed = ref(false);
const healthPayload = ref<Record<string, unknown>>({});

const routerDetailRoutes = computed<RouterDetailRoute[]>(() => [
  {
    name: "Overview",
    label: t("router.OverviewTab"),
    icon: FundOutlined,
  },
  {
    name: "TokenOverview",
    label: t("router.routerTokenOverallTitle"),
    icon: DatabaseOutlined,
  },
  {
    name: "LatencyOverview",
    label: t("router.routerLatencyOverallTitle"),
    icon: ClockCircleOutlined,
  },
  {
    name: "RouterTraffic",
    label: t("router.routerTrafficTitle"),
    icon: DeploymentUnitOutlined,
  },
  {
    name: "ProviderConfig",
    label: t("router.routerConfigProvidersTitle"),
    icon: CloudServerOutlined,
  },
  {
    name: "PluginsConfig",
    label: t("router.routerPluginConfigTitle"),
    icon: AppstoreOutlined,
  },
  {
    name: "PolicyConfig",
    label: t("router.routerPolicyConfigTitle"),
    icon: FileProtectOutlined,
  },
  {
    name: "StrategyConfig",
    label: t("router.routerStrategyConfigTitle"),
    icon: BranchesOutlined,
  },
]);

const routerHealthStatusText = computed(() => {
  const value = healthPayload.value.status;
  return value ? String(value) : t("router.routerEmptyValue");
});
const routerHealthStatusTone = computed(() => {
  const value = String(healthPayload.value.status || "").toLowerCase();
  return value === "healthy" ? "healthy" : "";
});

const toggleMenuCollapsed = () => {
  isMenuCollapsed.value = !isMenuCollapsed.value;
};

const fetchRouterHealth = async () => {
  const health = await getRouterHealth();
  healthPayload.value = (health || {}) as Record<string, unknown>;
};

onMounted(() => {
  void fetchRouterHealth().catch(() => undefined);
});
</script>

<style scoped lang="less">
.router-monitor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 100%;
  padding: 12px;
  overflow: hidden;
  color: var(--font-main-color);
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--color-primarySoft) 58%, transparent) 0%,
      color-mix(in srgb, var(--surface-panel-bg) 72%, transparent) 36%,
      color-mix(in srgb, var(--color-successSoft) 48%, transparent) 100%
    ),
    var(--bg-content-color);

  --router-line: color-mix(
    in srgb,
    var(--color-primary) 18%,
    var(--border-main-color) 82%
  );
  --router-panel-bg: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 92%,
    transparent
  );
  --router-menu-bg: color-mix(
    in srgb,
    var(--color-primarySoft) 78%,
    var(--surface-panel-bg-strong) 22%
  );
  --router-soft-panel: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 68%,
    transparent
  );
  --router-shadow: color-mix(in srgb, var(--bg-box-shadow) 38%, transparent);
}

.router-detail-page {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  color: var(--font-main-color);
}

.router-detail-body {
  display: grid;
  grid-template-columns: minmax(196px, 218px) minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--router-line);
  border-radius: 18px;
  background: var(--router-panel-bg);
  box-shadow: 0 18px 42px
    color-mix(in srgb, var(--router-shadow) 42%, transparent);
  transition: grid-template-columns 180ms ease;
}

.router-detail-body.collapsed-menu {
  grid-template-columns: 78px minmax(0, 1fr);
}

.router-detail-tabs {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  margin: 0;
  padding: 12px;
  overflow-x: hidden;
  overflow-y: auto;
  border-right: 1px solid var(--router-line);
  border-radius: 17px 0 0 17px;
  background: linear-gradient(
    165deg,
    var(--router-menu-bg) 0%,
    color-mix(
        in srgb,
        var(--router-menu-bg) 74%,
        var(--surface-panel-bg-strong)
      )
      100%
  );
  box-shadow: inset -1px 0 0
    color-mix(in srgb, var(--router-line) 72%, transparent);
}

.router-tabs-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 4px 10px;
  border-bottom: 1px solid
    color-mix(in srgb, var(--router-line) 82%, transparent);
}

.router-tabs-heading-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.router-tabs-heading span {
  color: var(--color-primary);
  font-size: var(--font-size-13);
  font-weight: 800;
  letter-spacing: 0.03em;
}

.router-tabs-heading small {
  color: var(--font-tip-color);
  font-size: var(--font-size-10);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.router-tabs-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, transparent);
  border-radius: 8px;
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 86%,
    transparent
  );
  color: var(--color-primary);
  cursor: pointer;
}

.router-tabs-toggle:hover {
  border-color: color-mix(in srgb, var(--color-primary) 42%, transparent);
  background: color-mix(in srgb, var(--color-primarySoft) 84%, transparent);
}

.router-detail-tab {
  position: relative;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  width: 100%;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 14px;
  background: transparent;
  color: var(--font-text-color);
  font-size: var(--font-size-12);
  line-height: 1.15;
  text-align: left;
  text-decoration: none;
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    box-shadow 160ms ease,
    color 160ms ease,
    transform 160ms ease;
}

.router-detail-tab:not(.active):hover {
  border-color: color-mix(in srgb, var(--color-primary) 18%, transparent);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 70%,
    transparent
  );
  transform: translateX(2px);
}

.router-detail-tab.active {
  border-color: color-mix(in srgb, var(--color-primary) 30%, transparent);
  background: linear-gradient(
    135deg,
    color-mix(
        in srgb,
        var(--color-primarySoft) 86%,
        var(--surface-panel-bg-strong)
      )
      0%,
    var(--surface-panel-bg-strong) 100%
  );
  color: var(--color-primary);
  box-shadow:
    inset 4px 0 0 var(--color-primary),
    0 10px 22px color-mix(in srgb, var(--router-shadow) 48%, transparent);
}

.router-tab-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 18%, transparent);
  border-radius: 12px;
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 76%,
    transparent
  );
  color: var(--color-primary);
  font-size: 16px;
}

.router-detail-tab.active .router-tab-icon {
  border-color: color-mix(in srgb, var(--color-primary) 30%, transparent);
  background: var(--color-primary);
  color: var(--color-white);
}

.router-tab-main {
  display: grid;
  min-width: 0;
}

.router-tab-label {
  overflow: hidden;
  color: var(--font-main-color);
  font-size: var(--font-size-14);
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.router-detail-tab.active .router-tab-label {
  color: var(--color-primary);
}

.router-detail-tabs.collapsed {
  padding: 12px 10px;
}

.router-detail-tabs.collapsed .router-tabs-heading {
  justify-content: center;
  padding: 0 0 8px;
}

.router-detail-tabs.collapsed .router-tabs-heading-copy,
.router-detail-tabs.collapsed .router-tab-main {
  display: none;
}

.router-detail-tabs.collapsed .router-detail-tab {
  grid-template-columns: 1fr;
  justify-items: center;
  min-height: 48px;
  padding: 8px;
}

.router-side-summary {
  display: grid;
  gap: 8px;
  margin-top: auto;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--router-line) 82%, transparent);
  border-radius: 14px;
  background: var(--router-soft-panel);
}

.router-side-status {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}

.router-side-status strong {
  overflow: hidden;
  color: var(--font-main-color);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.router-status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--color-error);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-error) 12%, transparent);
}

.router-status-dot.healthy {
  background: var(--color-success);
  box-shadow: 0 0 0 4px
    color-mix(in srgb, var(--color-success) 14%, transparent);
}

.router-detail-tabs.collapsed .router-side-summary {
  margin-top: auto;
  padding: 10px 6px;
}

.router-detail-tabs.collapsed .router-side-status {
  grid-template-columns: 1fr;
  justify-items: center;
  gap: 4px;
  text-align: center;
}

.router-detail-tabs.collapsed
  .router-side-status
  > span:not(.router-status-dot) {
  display: none;
}

.router-detail-route-panel {
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 16px;
  overflow: auto;
  border-radius: 0 17px 17px 0;
  background: var(--router-panel-bg);
}

@media (max-width: 1080px) {
  .router-detail-body {
    grid-template-columns: minmax(184px, 204px) minmax(0, 1fr);
  }

  .router-detail-body.collapsed-menu {
    grid-template-columns: 72px minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .router-monitor {
    height: auto;
    min-height: 100%;
    padding: 10px;
    overflow: auto;
  }

  .router-detail-page {
    overflow: visible;
  }

  .router-detail-body {
    display: flex;
    flex-direction: column;
    min-height: auto;
    overflow: visible;
    border-radius: 16px;
  }

  .router-detail-tabs,
  .router-detail-tabs.collapsed {
    flex-direction: row;
    width: auto;
    min-width: 0;
    padding: 10px;
    overflow-x: auto;
    overflow-y: hidden;
    gap: 8px;
    border-right: 0;
    border-bottom: 1px solid var(--router-line);
    border-radius: 15px 15px 0 0;
  }

  .router-tabs-heading,
  .router-side-summary {
    display: none;
  }

  .router-detail-tab,
  .router-detail-tabs.collapsed .router-detail-tab {
    grid-template-columns: 34px minmax(0, 1fr);
    justify-items: initial;
    flex: 0 0 230px;
    min-height: 64px;
    padding: 9px;
    border-radius: 12px;
    background: color-mix(
      in srgb,
      var(--surface-panel-bg-strong) 88%,
      transparent
    );
  }

  .router-detail-tabs.collapsed .router-tab-main {
    display: grid;
  }

  .router-detail-tab.active {
    box-shadow: inset 0 -3px 0 var(--color-primary);
  }

  .router-detail-route-panel {
    min-width: auto;
    height: auto;
    padding: 14px;
    overflow: visible;
    border: 0;
    border-radius: 0 0 15px 15px;
  }
}

@media (max-width: 520px) {
  .router-detail-tab,
  .router-detail-tabs.collapsed .router-detail-tab {
    flex-basis: 82%;
  }
}
</style>
