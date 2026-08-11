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
          role="tablist"
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
          <button
            v-for="detailTab in routerDetailTabs"
            :key="detailTab.key"
            type="button"
            class="router-detail-tab"
            :class="{ active: activeDetailTab === detailTab.key }"
            role="tab"
            :aria-selected="activeDetailTab === detailTab.key"
            :title="isMenuCollapsed ? detailTab.label : ''"
            @click="activeDetailTab = detailTab.key"
          >
            <span class="router-tab-icon">
              <component :is="detailTab.icon" />
            </span>
            <span class="router-tab-main">
              <span class="router-tab-label">{{ detailTab.label }}</span>
            </span>
          </button>

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

        <section class="router-detail-tab-panel">
          <OverviewTab
            v-show="activeDetailTab === 'overview'"
            :drawer-data="overviewDrawerData"
            @refresh="handleRefreshMetrics"
            @reset="handleResetMetrics"
          />
          <RouterProviderConfigTab
            v-show="activeDetailTab === 'config'"
            :drawer-data="configDrawerData"
            @reload="handleReloadConfig"
          />
          <TokenOverviewTab
            v-show="activeDetailTab === 'tokens'"
            :drawer-data="tokenDrawerData"
          />
          <LatencyOverviewTab
            v-show="activeDetailTab === 'latency'"
            :drawer-data="latencyDrawerData"
          />
        </section>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, createVNode, onMounted, onUnmounted, ref, watch } from "vue";
import type { Component } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { Modal } from "ant-design-vue";
import {
  ClockCircleOutlined,
  DatabaseOutlined,
  ExclamationCircleFilled,
  FundOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ToolOutlined,
} from "@ant-design/icons-vue";
import {
  getRouterHealth,
  getRouterMetrics,
  reloadRouterConfig,
  resetRouterMetrics,
} from "@/api/router";
import {
  LatencyOverviewTab,
  OverviewTab,
  RouterProviderConfigTab,
  TokenOverviewTab,
} from "./components";
import type {
  ConfigProviderRow,
  DistributionProviderRow,
  LatencyProviderRow,
  TokenProviderRow,
} from "./type";

interface RouterMonitorData {
  health: any;
  metrics: any;
  config: any;
}

type RouterDetailTabKey = "overview" | "tokens" | "latency" | "config";

interface RouterDetailTab {
  key: RouterDetailTabKey;
  label: string;
  icon: Component;
}

interface TokenProviderMetric {
  provider: string;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  requestCount: number | null;
  avgTokensPerRequest: number | null;
  requestShare: number | null;
  tokenShare: number | null;
}

interface RouterTokenBreakdown {
  systemPromptTokens: number;
  toolSchemaTokens: number;
  contextTokens: number;
  overallTokens: number;
}

const calculateCompressionDelta = (before: number, after: number) =>
  Math.max(before - after, 0);

const calculateCompressionPercent = (before: number, after: number) =>
  before ? (calculateCompressionDelta(before, after) / before) * 100 : 0;

const createInitialData = (): RouterMonitorData => ({
  health: {},
  metrics: {},
  config: {},
});

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const isResetting = ref(false);
const isReloading = ref(false);
const isMetricsRefreshing = ref(false);
const isMenuCollapsed = ref(false);
const routerData = ref<RouterMonitorData>(createInitialData());
const activeDetailTab = ref<RouterDetailTabKey>("overview");
let metricsPollingTimer: number | null = null;
const tabQueryKey = "tab";

const isRouterDetailTabKey = (value: unknown): value is RouterDetailTabKey =>
  value === "overview" ||
  value === "tokens" ||
  value === "latency" ||
  value === "config";

const parseTabQueryValue = (value: unknown): RouterDetailTabKey | null => {
  const rawValue = Array.isArray(value) ? value[0] : value;
  return isRouterDetailTabKey(rawValue) ? rawValue : null;
};

const routerDetailTabs = computed<RouterDetailTab[]>(() => [
  {
    key: "overview",
    label: t("router.OverviewTab"),
    icon: FundOutlined,
  },
  {
    key: "tokens",
    label: t("router.routerTokenOverallTitle"),
    icon: DatabaseOutlined,
  },
  {
    key: "latency",
    label: t("router.routerLatencyOverallTitle"),
    icon: ClockCircleOutlined,
  },
  {
    key: "config",
    label: t("router.routerConfigProvidersTitle"),
    icon: ToolOutlined,
  },
]);

const toggleMenuCollapsed = () => {
  isMenuCollapsed.value = !isMenuCollapsed.value;
};

watch(
  () => route.query[tabQueryKey],
  (tabQueryValue) => {
    const queryTab = parseTabQueryValue(tabQueryValue);
    if (queryTab && queryTab !== activeDetailTab.value) {
      activeDetailTab.value = queryTab;
    }
  },
  { immediate: true },
);

watch(
  activeDetailTab,
  (tabKey) => {
    if (parseTabQueryValue(route.query[tabQueryKey]) === tabKey) return;
    void router.replace({
      query: {
        ...route.query,
        [tabQueryKey]: tabKey,
      },
    });
  },
  { immediate: true },
);

const normalizeNumber = (value: unknown) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : 0;
};

const normalizeNullableNumber = (value: unknown) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
};

// Format large numbers in compact notation (e.g. 1200 -> 1.2K).
const formatCompactNumber = (value: unknown) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(normalizeNumber(value));

// Normalize latency-like values and render with ms suffix.
const formatLatency = (value: unknown) =>
  `${normalizeNumber(value).toFixed(1)} ms`;

// Format ratio values in [0, 1] to percentage text.
const formatPercent = (value: unknown, digits = 1) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? `${(numberValue * 100).toFixed(digits)}%`
    : t("router.routerEmptyValue");
};

// Format values that are already percentage numbers.
const formatRatioPercent = (value: unknown, digits = 1) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? `${numberValue.toFixed(digits)}%`
    : t("router.routerEmptyValue");
};

// Nullable wrappers used by table/card rendering.
const formatCompactNullable = (value: number | null) =>
  value === null ? t("router.routerEmptyValue") : formatCompactNumber(value);
const formatLatencyNullable = (value: number | null) =>
  value === null ? t("router.routerEmptyValue") : `${value.toFixed(1)} ms`;

// Show numeric values (including 0); use empty placeholder only for invalid values.
const formatMaybeCompact = (value: unknown) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? formatCompactNumber(numberValue)
    : t("router.routerEmptyValue");
};

// Generic display formatter for mixed-value config fields.
const formatDisplayValue = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "boolean")
    return value ? t("common.yes") : t("common.no");
  if (typeof value === "object") {
    if (Array.isArray(value) && !value.length) return "--";
    if (!Array.isArray(value) && !Object.keys(value as object).length)
      return "--";
    return JSON.stringify(value);
  }
  return String(value);
};

const providerPalette = [
  "#2f6fed",
  "#20a162",
  "#f59e0b",
  "#8b5cf6",
  "#ef4444",
  "#64748b",
];
const providerColor = (index: number) =>
  providerPalette[index % providerPalette.length];
const maxNullableValue = <T,>(rows: T[], pick: (row: T) => number | null) =>
  rows.reduce(
    (maxValue, row) => Math.max(maxValue, normalizeNumber(pick(row))),
    0,
  );
const percentOfMax = (value: number | null, maxValue: number) =>
  maxValue ? Math.max((normalizeNumber(value) / maxValue) * 100, 3) : 0;

const metricsPayload = computed(() => routerData.value.metrics || {});
const healthPayload = computed(() => routerData.value.health || {});
const routingStats = computed(() => metricsPayload.value.routing_stats || {});
const tokenMetrics = computed(() => metricsPayload.value.token_metrics || {});
const tokenOverall = computed(() => tokenMetrics.value.overall || {});
const latencyOverall = computed(
  () => metricsPayload.value.latency_metrics?.overall || {},
);
const routerHealthStatusText = computed(() => {
  const value = healthPayload.value.status;
  return value ? String(value) : t("router.routerEmptyValue");
});
const routerHealthStatusTone = computed(() => {
  const value = String(healthPayload.value.status || "").toLowerCase();
  return value === "healthy" ? "healthy" : "";
});

const tokenMetricsByProvider = computed<TokenProviderMetric[]>(() => {
  const byProvider = tokenMetrics.value.by_provider;
  if (!byProvider || typeof byProvider !== "object") return [];

  return Object.entries(byProvider as Record<string, unknown>).map(
    ([provider, rawMetric]) => {
      const metric =
        rawMetric && typeof rawMetric === "object"
          ? (rawMetric as Record<string, unknown>)
          : {};
      return {
        provider,
        inputTokens: normalizeNullableNumber(metric.input_tokens),
        outputTokens: normalizeNullableNumber(metric.output_tokens),
        totalTokens: normalizeNullableNumber(metric.total_tokens),
        requestCount: normalizeNullableNumber(metric.request_count),
        avgTokensPerRequest: normalizeNullableNumber(
          metric.avg_tokens_per_request,
        ),
        requestShare: normalizeNullableNumber(metric.request_share),
        tokenShare: normalizeNullableNumber(metric.token_share),
      };
    },
  );
});

const buildTokenProviderRows = (
  rows: TokenProviderMetric[],
  resolveColor: (row: TokenProviderMetric, index: number) => string,
): TokenProviderRow[] => {
  const maxRequests = maxNullableValue(rows, (row) => row.requestCount);
  const maxTotalTokens = maxNullableValue(rows, (row) => row.totalTokens);
  const maxInputTokens = maxNullableValue(rows, (row) => row.inputTokens);
  const maxOutputTokens = maxNullableValue(rows, (row) => row.outputTokens);
  const totalInputTokens = rows.reduce(
    (sum, row) => sum + normalizeNumber(row.inputTokens),
    0,
  );
  const totalOutputTokens = rows.reduce(
    (sum, row) => sum + normalizeNumber(row.outputTokens),
    0,
  );

  return rows.map((row, index) => ({
    ...row,
    color: resolveColor(row, index),
    requestBarPercent: percentOfMax(row.requestCount, maxRequests),
    totalBarPercent: percentOfMax(row.totalTokens, maxTotalTokens),
    inputBarPercent: percentOfMax(row.inputTokens, maxInputTokens),
    outputBarPercent: percentOfMax(row.outputTokens, maxOutputTokens),
    requestShareText: formatPercent(row.requestShare),
    tokenShareText: formatPercent(row.tokenShare),
    inputShareText: totalInputTokens
      ? formatRatioPercent(
          (normalizeNumber(row.inputTokens) / totalInputTokens) * 100,
        )
      : t("router.routerEmptyValue"),
    outputShareText: totalOutputTokens
      ? formatRatioPercent(
          (normalizeNumber(row.outputTokens) / totalOutputTokens) * 100,
        )
      : t("router.routerEmptyValue"),
  }));
};

const latencyProviderRows = computed<LatencyProviderRow[]>(() => {
  const byProvider = metricsPayload.value.latency_metrics?.by_provider;
  if (!byProvider || typeof byProvider !== "object") return [];

  return Object.entries(byProvider as Record<string, unknown>).map(
    ([provider, rawMetric]) => {
      const metric =
        rawMetric && typeof rawMetric === "object"
          ? (rawMetric as Record<string, unknown>)
          : {};
      return {
        provider,
        avgLatencyMs: normalizeNullableNumber(metric.avg_latency_ms),
        avgTtftMs: normalizeNullableNumber(metric.avg_ttft_ms),
        avgTpotMs: normalizeNullableNumber(metric.avg_tpot_ms),
        ttftCount: normalizeNullableNumber(metric.ttft_count),
        tpotCount: normalizeNullableNumber(metric.tpot_count),
      };
    },
  );
});

interface DistributionMetricRow {
  provider: string;
  requestCount: number;
}

const buildDistributionRows = (
  rows: DistributionMetricRow[],
  resolveColor: (provider: string, index: number) => string,
): DistributionProviderRow[] => {
  const providerTotal = rows.reduce((sum, row) => sum + row.requestCount, 0);
  const requestTotal = providerTotal || totalRequests.value;

  return rows.map((row, index) => {
    const percent = requestTotal ? (row.requestCount / requestTotal) * 100 : 0;
    return {
      provider: row.provider,
      requestCount: row.requestCount,
      percent,
      color: resolveColor(row.provider, index),
      requestText: `${formatCompactNumber(row.requestCount)} (${percent.toFixed(1)}%)`,
    };
  });
};

const buildDistributionFallbackRows = (
  rows: TokenProviderRow[],
  resolveColor: (provider: string, index: number) => string,
): DistributionProviderRow[] =>
  rows
    .filter((row) => normalizeNumber(row.requestCount) > 0)
    .map((row, index) => ({
      provider: row.provider,
      requestCount: normalizeNumber(row.requestCount),
      percent: normalizeNumber(row.requestShare) * 100,
      color: resolveColor(row.provider, index),
      requestText: `${formatCompactNullable(row.requestCount)} (${(normalizeNumber(row.requestShare) * 100).toFixed(1)}%)`,
    }));

const sortedTokenProviderRows = computed<TokenProviderRow[]>(() => {
  const rows = [...tokenMetricsByProvider.value].sort((left, right) => {
    const leftShare = left.requestShare ?? Number.NEGATIVE_INFINITY;
    const rightShare = right.requestShare ?? Number.NEGATIVE_INFINITY;
    if (leftShare !== rightShare) return rightShare - leftShare;
    return left.provider.localeCompare(right.provider);
  });
  return buildTokenProviderRows(rows, (_, index) => providerColor(index));
});

const sortedLatencyProviderRows = computed<LatencyProviderRow[]>(() => {
  return [...latencyProviderRows.value].sort((left, right) => {
    const leftLatency = left.avgLatencyMs ?? Number.POSITIVE_INFINITY;
    const rightLatency = right.avgLatencyMs ?? Number.POSITIVE_INFINITY;
    if (leftLatency !== rightLatency) return leftLatency - rightLatency;
    return left.provider.localeCompare(right.provider);
  });
});

const overviewProviderOrder = computed(() => {
  if (tokenMetricsByProvider.value.length) {
    return tokenMetricsByProvider.value.map((row) => row.provider);
  }

  const routingByProvider = routingStats.value.by_provider;
  if (routingByProvider && typeof routingByProvider === "object") {
    return Object.keys(routingByProvider as Record<string, unknown>);
  }

  const latencyByProvider = metricsPayload.value.latency_metrics?.by_provider;
  if (latencyByProvider && typeof latencyByProvider === "object") {
    return Object.keys(latencyByProvider as Record<string, unknown>);
  }

  return [] as string[];
});

const overviewProviderColorMap = computed(() => {
  const colorMap = new Map<string, string>();
  overviewProviderOrder.value.forEach((provider, index) => {
    colorMap.set(provider, providerColor(index));
  });
  return colorMap;
});

const overviewProviderColor = (provider: string, fallbackIndex: number) =>
  overviewProviderColorMap.value.get(provider) ?? providerColor(fallbackIndex);

const orderedTokenProviderRows = computed<TokenProviderRow[]>(() => {
  const rows = [...tokenMetricsByProvider.value];
  return buildTokenProviderRows(rows, (row, index) =>
    overviewProviderColor(row.provider, index),
  );
});

const orderedDistributionProviderRows = computed<DistributionProviderRow[]>(
  () => {
    const byProvider = routingStats.value.by_provider;
    if (byProvider && typeof byProvider === "object") {
      const rawRows = Object.entries(byProvider as Record<string, unknown>)
        .map(([provider, count]) => ({
          provider,
          requestCount: normalizeNumber(count),
        }))
        .filter((row) => row.requestCount > 0);
      return buildDistributionRows(rawRows, overviewProviderColor);
    }

    return buildDistributionFallbackRows(
      orderedTokenProviderRows.value,
      overviewProviderColor,
    );
  },
);

const totalRequests = computed(() =>
  normalizeNumber(routingStats.value.total_requests),
);
const totalTokenRequestCount = computed(() => {
  const overallRequests = normalizeNumber(tokenOverall.value.total_requests);
  if (overallRequests > 0) return overallRequests;
  return tokenMetricsByProvider.value.reduce(
    (sum, providerMetric) => sum + normalizeNumber(providerMetric.requestCount),
    0,
  );
});

const normalizeRouterTokenBreakdown = (
  value: unknown,
): RouterTokenBreakdown => {
  const metric =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  return {
    systemPromptTokens: normalizeNumber(metric.system_prompt_tokens),
    toolSchemaTokens: normalizeNumber(metric.tool_schema_tokens),
    contextTokens: normalizeNumber(metric.context_tokens),
    overallTokens: normalizeNumber(metric.overall_tokens),
  };
};
const beforeRouterTokens = computed(() =>
  normalizeRouterTokenBreakdown(tokenMetrics.value.before_router),
);
const afterRouterTokens = computed(() =>
  normalizeRouterTokenBreakdown(tokenMetrics.value.after_router),
);
const routerCompressedTokens = computed(() =>
  calculateCompressionDelta(
    beforeRouterTokens.value.overallTokens,
    afterRouterTokens.value.overallTokens,
  ),
);
const routerCompressionPercent = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.overallTokens,
    afterRouterTokens.value.overallTokens,
  ),
);
const routerCompressionRestPercent = computed(() =>
  beforeRouterTokens.value.overallTokens
    ? (afterRouterTokens.value.overallTokens /
        beforeRouterTokens.value.overallTokens) *
      100
    : 0,
);

const configProviders = computed<ConfigProviderRow[]>(() =>
  Array.isArray(routerData.value.config?.providers)
    ? routerData.value.config.providers
    : [],
);
const totalRequestsText = computed(() =>
  formatCompactNumber(routingStats.value.total_requests),
);
const totalTokensText = computed(() =>
  formatMaybeCompact(tokenOverall.value.total_tokens),
);
const totalInputTokensText = computed(() =>
  formatMaybeCompact(tokenOverall.value.total_input_tokens),
);
const totalOutputTokensText = computed(() =>
  formatMaybeCompact(tokenOverall.value.total_output_tokens),
);
const totalRequestsMetricText = computed(() =>
  formatMaybeCompact(totalTokenRequestCount.value),
);
const avgTokensPerRequestText = computed(() => {
  const value = tokenOverall.value.avg_tokens_per_request;
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? String(value)
    : t("router.routerEmptyValue");
});
const avgLatencyText = computed(() =>
  formatLatency(latencyOverall.value.avg_latency_ms),
);
const avgTtftText = computed(() =>
  formatLatency(latencyOverall.value.avg_ttft_ms),
);
const avgTpotText = computed(() =>
  formatLatency(latencyOverall.value.avg_tpot_ms),
);
const ttftCountText = computed(() =>
  formatMaybeCompact(latencyOverall.value.ttft_count),
);
const tpotCountText = computed(() =>
  formatMaybeCompact(latencyOverall.value.tpot_count),
);
const systemPromptCompressionPercent = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.systemPromptTokens,
    afterRouterTokens.value.systemPromptTokens,
  ),
);
const toolSchemaCompressionPercent = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.toolSchemaTokens,
    afterRouterTokens.value.toolSchemaTokens,
  ),
);
const contextCompressionPercent = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.contextTokens,
    afterRouterTokens.value.contextTokens,
  ),
);

const overviewDrawerData = computed(() => ({
  distributionProviderRows: orderedDistributionProviderRows.value,
  tokenProviderRows: orderedTokenProviderRows.value,
  totalRequestsText: totalRequestsText.value,
  totalTokensText: totalTokensText.value,
  totalInputTokens: normalizeNumber(tokenOverall.value.total_input_tokens),
  totalOutputTokens: normalizeNumber(tokenOverall.value.total_output_tokens),
  latencyProviderRows: latencyProviderRows.value,
  avgLatencyMs: normalizeNullableNumber(latencyOverall.value.avg_latency_ms),
  avgTtftMs: normalizeNullableNumber(latencyOverall.value.avg_ttft_ms),
  avgTpotMs: normalizeNullableNumber(latencyOverall.value.avg_tpot_ms),
  beforeRouterTokensText: formatMaybeCompact(
    beforeRouterTokens.value.overallTokens,
  ),
  afterRouterTokensText: formatMaybeCompact(
    afterRouterTokens.value.overallTokens,
  ),
  routerCompressedTokensText: formatMaybeCompact(routerCompressedTokens.value),
  routerCompressionPercent: routerCompressionPercent.value,
  routerCompressionPercentText: formatRatioPercent(
    routerCompressionPercent.value,
  ),
  routerCompressionRestPercent: routerCompressionRestPercent.value,
  routerCompressionRestPercentText: formatRatioPercent(
    routerCompressionRestPercent.value,
  ),
  systemPromptBeforeTokensText: formatMaybeCompact(
    beforeRouterTokens.value.systemPromptTokens,
  ),
  systemPromptAfterTokensText: formatMaybeCompact(
    afterRouterTokens.value.systemPromptTokens,
  ),
  systemPromptCompressedTokensText: formatMaybeCompact(
    calculateCompressionDelta(
      beforeRouterTokens.value.systemPromptTokens,
      afterRouterTokens.value.systemPromptTokens,
    ),
  ),
  systemPromptCompressionPercent: systemPromptCompressionPercent.value,
  systemPromptCompressionPercentText: formatRatioPercent(
    systemPromptCompressionPercent.value,
  ),
  toolSchemaBeforeTokensText: formatMaybeCompact(
    beforeRouterTokens.value.toolSchemaTokens,
  ),
  toolSchemaAfterTokensText: formatMaybeCompact(
    afterRouterTokens.value.toolSchemaTokens,
  ),
  toolSchemaCompressedTokensText: formatMaybeCompact(
    calculateCompressionDelta(
      beforeRouterTokens.value.toolSchemaTokens,
      afterRouterTokens.value.toolSchemaTokens,
    ),
  ),
  toolSchemaCompressionPercent: toolSchemaCompressionPercent.value,
  toolSchemaCompressionPercentText: formatRatioPercent(
    toolSchemaCompressionPercent.value,
  ),
  contextBeforeTokensText: formatMaybeCompact(
    beforeRouterTokens.value.contextTokens,
  ),
  contextAfterTokensText: formatMaybeCompact(
    afterRouterTokens.value.contextTokens,
  ),
  contextCompressedTokensText: formatMaybeCompact(
    calculateCompressionDelta(
      beforeRouterTokens.value.contextTokens,
      afterRouterTokens.value.contextTokens,
    ),
  ),
  contextCompressionPercent: contextCompressionPercent.value,
  contextCompressionPercentText: formatRatioPercent(
    contextCompressionPercent.value,
  ),
  isMetricsRefreshing: isMetricsRefreshing.value,
  isResetting: isResetting.value,
}));

const configDrawerData = computed(() => ({
  providers: configProviders.value,
  latencyProviderRows: latencyProviderRows.value,
  isReloading: isReloading.value,
  formatDisplayValue,
  formatLatencyNullable,
}));

const tokenDrawerData = computed(() => ({
  providerRows: sortedTokenProviderRows.value,
  totalTokensText: totalTokensText.value,
  totalInputTokensText: totalInputTokensText.value,
  totalOutputTokensText: totalOutputTokensText.value,
  totalRequestsMetricText: totalRequestsMetricText.value,
  avgTokensPerRequestText: avgTokensPerRequestText.value,
  formatCompactNullable,
  normalizeNumber,
}));

const latencyDrawerData = computed(() => ({
  providerRows: sortedLatencyProviderRows.value,
  avgLatencyText: avgLatencyText.value,
  avgTtftText: avgTtftText.value,
  avgTpotText: avgTpotText.value,
  ttftCountText: ttftCountText.value,
  tpotCountText: tpotCountText.value,
  formatLatencyNullable,
  formatCompactNullable,
  latencyToneClass,
}));

const latencyToneClass = (value: number | null) => {
  if (value === null) return "empty";
  const overall = normalizeNumber(latencyOverall.value.avg_latency_ms);
  if (!overall) return "neutral";
  if (value <= overall * 0.9) return "good";
  if (value >= overall * 1.1) return "bad";
  return "neutral";
};
const handleReloadConfig = async () => {
  if (isReloading.value) return;
  isReloading.value = true;
  try {
    await reloadRouterConfig();
  } finally {
    isReloading.value = false;
  }
};

const fetchRouterMetrics = async () => {
  const metrics = await getRouterMetrics();
  routerData.value.metrics = metrics;
  return metrics;
};

const fetchRouterHealth = async () => {
  const health = await getRouterHealth();
  routerData.value.health = health;
  return health;
};

const fetchRouterData = async () => {
  await Promise.all([fetchRouterMetrics(), fetchRouterHealth()]);
};

const fetchRouterMetricsData = async () => {
  await fetchRouterMetrics();
};

const handleRefreshMetrics = async () => {
  if (isMetricsRefreshing.value) return;
  isMetricsRefreshing.value = true;
  try {
    await fetchRouterMetricsData();
  } finally {
    isMetricsRefreshing.value = false;
  }
};

const handleResetMetrics = async () => {
  if (isResetting.value) return;
  Modal.confirm({
    zIndex: 1500,
    mask: true,
    title: t("common.reset"),
    icon: createVNode(ExclamationCircleFilled, { class: "warring-icon" }),
    content: t("router.resetStats"),
    okText: t("common.reset"),
    cancelText: t("common.cancel"),
    async onOk() {
      if (isResetting.value) return;
      isResetting.value = true;
      try {
        await resetRouterMetrics();
        await fetchRouterMetricsData();
      } finally {
        isResetting.value = false;
      }
    },
  });
};

onMounted(() => {
  void fetchRouterData();
  metricsPollingTimer = window.setInterval(() => {
    void fetchRouterMetricsData();
  }, 5000);
});

onUnmounted(() => {
  if (metricsPollingTimer !== null) {
    window.clearInterval(metricsPollingTimer);
    metricsPollingTimer = null;
  }
});
</script>

<style scoped lang="less">
.router-monitor {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

  --router-cloud: color-mix(
    in srgb,
    var(--color-warning-strong) 88%,
    var(--font-main-color) 12%
  );
  --router-line: color-mix(
    in srgb,
    var(--color-primary) 18%,
    var(--border-main-color) 82%
  );
  --router-top-line: color-mix(
    in srgb,
    var(--color-primary) 28%,
    var(--border-main-color) 72%
  );
  --router-top-glow: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 74%,
    transparent
  );
  --router-panel-bg: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 92%,
    transparent
  );
  --router-rail-bg: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 72%,
    var(--color-primarySoft) 28%
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

.route-card,
.metric-strip article {
  border: 1px solid var(--router-line);
  background: linear-gradient(
    180deg,
    color-mix(
        in srgb,
        var(--surface-panel-bg-strong) 94%,
        var(---color-primaryBg) 6%
      )
      0%,
    color-mix(in srgb, var(--surface-panel-bg-strong) 98%, transparent) 100%
  );
  box-shadow: 0 10px 20px var(--router-shadow);
}

.router-runtime-summary {
  display: flex;
  flex-direction: column;
  padding: 10px;
  border: 1px solid
    color-mix(in srgb, var(--color-success) 20%, var(--router-line) 80%);
  border-radius: 12px;
  background: color-mix(
    in srgb,
    var(--color-successSoft) 36%,
    var(--surface-panel-bg-strong) 64%
  );
}

.router-runtime-icon,
.section-icon,
.router-icon-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.router-runtime-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-successSoft) 50%, transparent);
  border: 1px solid
    color-mix(in srgb, var(--color-success) 20%, var(--router-line) 80%);
  color: var(--color-success);
  font-size: 14px;
}

.router-runtime-content {
  flex: 1;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.router-runtime-panel {
  flex: 1;
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 80%, transparent);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 86%,
    transparent
  );
}

.router-runtime-panel-title,
.section-title {
  color: var(--font-main-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}

.router-runtime-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding: 6px 8px;
  border-radius: 10px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 80%, transparent);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 82%,
    transparent
  );
}

.router-runtime-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-tip-color);
  font-size: var(--font-size-10);
  font-weight: 600;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  color: var(--color-success);
  font-size: var(--font-size-11);
}

.status-pill.danger {
  color: var(--color-error, var(--color-errorBg));
}

.status-icon {
  font-size: 12px;
}

.router-max-concurrency {
  color: var(--font-main-color);
  font-size: var(--font-size-14);
  font-weight: 600;
}

.router-metrics-section,
.router-default-distribution {
  padding: 10px;
  border: 1px solid var(--router-line);
  border-radius: 14px;
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 94%,
    var(---color-primaryBg) 6%
  );
  box-shadow: 0 10px 20px var(--router-shadow);
}

.router-section-header,
.section-heading,
.distribution-heading,
.router-more-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.router-section-header,
.distribution-heading,
.router-more-row {
  justify-content: space-between;
}

.router-section-header,
.section-heading {
  margin-bottom: 8px;
}

.router-section-heading {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
  font-weight: 600;
}

.section-icon {
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, transparent);
  background: color-mix(in srgb, var(--color-primarySoft) 82%, transparent);
  color: var(--color-primary);
}

.router-icon-action {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--color-primary) 20%, transparent);
  border-radius: 7px;
  background: color-mix(
    in srgb,
    var(--color-primary) 8%,
    var(--surface-panel-bg-strong)
  );
  color: var(--color-primary);
  cursor: pointer;
}

.router-icon-action.danger {
  color: var(--color-error);
  background: color-mix(
    in srgb,
    var(--color-error, var(--color-errorBg)) 8%,
    var(--surface-panel-bg-strong)
  );
}

.router-icon-action:disabled,
.router-more-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-strip article {
  min-width: 0;
  padding: 10px;
  border-radius: 14px;
}

.metric-strip span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
  color: var(--font-tip-color);
  font-size: var(--font-size-10);
  font-weight: 600;
}

.metric-strip .metric-value {
  margin-bottom: 0;
  color: var(--font-main-color);
  font-size: var(--font-size-16);
  line-height: 1;
  font-weight: 600;
}

.metric-strip .saving .metric-value {
  color: var(--color-success);
}
.metric-strip .average .metric-value {
  color: var(--color-warning-strong);
}
.metric-strip .latency .metric-value {
  color: var(--color-primary);
}

.distribution-heading {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}

.topology-value {
  color: var(--font-main-color);
  font-weight: 600;
  text-align: right;
}

.distribution-body {
  margin-top: 8px;
  min-width: 0;
}

.distribution-metric-card {
  min-width: 0;
  padding: 8px 12px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 76%, transparent);
  border-radius: 12px;
  background: color-mix(
    in srgb,
    var(--surface-card-bg) 72%,
    var(--surface-panel-bg-strong) 28%
  );
}

.distribution-metric-body {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.routing-pie {
  position: relative;
  flex: 0 0 80px;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 0 1px
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
}

.routing-pie::before {
  content: "";
  position: absolute;
  inset: 16px;
  border-radius: inherit;
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 94%,
    transparent
  );
}

.routing-pie-center {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 2px;
  text-align: center;
}

.routing-pie-center strong {
  color: var(--font-main-color);
  font-size: var(--font-size-12);
  font-weight: 600;
}

.routing-pie-center small {
  color: var(--font-tip-color);
  font-size: 9px;
  font-weight: 600;
}

.distribution-legend {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 5px;
}

.distribution-row {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: var(--font-size-11);
}

.distribution-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.distribution-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-text-color);
}

.distribution-row strong {
  color: var(--font-main-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}

.router-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 72px;
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}

.router-more-row {
  position: sticky;
  bottom: 0;
  z-index: 3;
  margin-top: auto;
  padding: 10px 0 0;
  background: linear-gradient(
    180deg,
    transparent 0%,
    var(--surface-panel-bg-strong) 42%,
    var(--surface-panel-bg-strong) 100%
  );
}

.router-more-button,
.router-drawer-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 32px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, transparent);
  border-radius: 999px;
  background: color-mix(
    in srgb,
    var(--color-primary) 10%,
    var(--surface-panel-bg-strong)
  );
  color: var(--color-primary);
  font-size: var(--font-size-11);
  font-weight: 600;
  cursor: pointer;
}

.router-more-button {
  flex: 0 0 auto;
  min-width: 132px;
  padding: 7px 10px;
}

.router-drawer-close {
  flex: 0 0 auto;
  padding: 7px 10px;
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
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(196px, 218px) minmax(0, 1fr);
  gap: 0;
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
  overflow-x: hidden;
  overflow-y: auto;
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
  flex: 0 0 auto;
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

.router-detail-tabs.collapsed .router-tabs-heading-copy {
  display: none;
}

.router-detail-tabs.collapsed .router-detail-tab {
  grid-template-columns: 1fr;
  justify-items: center;
  min-height: 48px;
  padding: 8px;
}

.router-detail-tabs.collapsed .router-tab-main {
  display: none;
}

.router-detail-tabs.collapsed .router-detail-tab::after {
  display: none;
}

.router-detail-tabs.collapsed .router-side-summary {
  display: grid;
  margin-top: auto;
  padding: 10px 6px;
  gap: 6px;
}

.router-detail-tabs.collapsed .router-side-status,
.router-detail-tabs.collapsed .router-side-stat {
  grid-template-columns: 1fr;
  justify-items: center;
  text-align: center;
  gap: 4px;
}

.router-detail-tabs.collapsed
  .router-side-status
  > span:not(.router-status-dot),
.router-detail-tabs.collapsed .router-side-stat > span {
  display: none;
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

.router-side-status,
.router-side-stat {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}

.router-side-status strong,
.router-side-stat strong {
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

.router-detail-tab-panel {
  min-height: 0;
  min-width: 0;
  height: 100%;
  padding: 16px;
  border-radius: 0 17px 17px 0;
  background: var(--router-panel-bg);
  overflow: auto;
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

  .router-runtime-content,
  .metric-strip {
    grid-template-columns: 1fr;
  }

  .router-detail-body {
    display: flex;
    flex-direction: column;
    min-height: auto;
    overflow: visible;
    border-radius: 16px;
  }

  .router-detail-tabs {
    flex-direction: row;
    width: auto;
    min-width: 0;
    padding: 10px;
    border-right: 0;
    border-bottom: 1px solid var(--router-line);
    border-radius: 15px 15px 0 0;
    overflow-x: auto;
    overflow-y: hidden;
    gap: 8px;
  }

  .router-tabs-heading,
  .router-side-summary {
    display: none;
  }

  .router-detail-tab {
    grid-template-columns: 34px minmax(0, 1fr);
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

  .router-detail-tab.active {
    box-shadow: inset 0 -3px 0 var(--color-primary);
  }

  .router-tabs-toggle {
    display: none;
  }

  .router-detail-tab-panel {
    min-width: auto;
    height: auto;
    padding: 14px;
    border: 0;
    border-radius: 0 0 15px 15px;
    overflow: visible;
  }
}
@media (max-width: 520px) {
  .router-detail-tab {
    flex-basis: 82%;
  }
}
</style>
