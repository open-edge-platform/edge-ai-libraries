<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->
<template>
  <div
    ref="wrapper"
    class="traffic-graph-wrap"
    :class="{ fullscreen: isFullscreen }"
  >
    <div class="graph-toolbar">
      <span
        >{{ t(`router.traffic.${mode}`) }} ·
        {{ t("router.traffic.topology") }}</span
      >
      <div class="graph-actions">
        <a-checkbox v-model:checked="showLabels">{{
          t("router.traffic.labels")
        }}</a-checkbox>
        <a-button
          type="text"
          :title="t('router.traffic.zoomOut')"
          :aria-label="t('router.traffic.zoomOut')"
          @click="zoom(0.8)"
        >
          <template #icon><ZoomOutOutlined /></template>
        </a-button>
        <a-button
          type="text"
          :title="t('router.traffic.zoomIn')"
          :aria-label="t('router.traffic.zoomIn')"
          @click="zoom(1.25)"
        >
          <template #icon><ZoomInOutlined /></template>
        </a-button>
        <a-button
          type="text"
          :title="t('router.traffic.fit')"
          :aria-label="t('router.traffic.fit')"
          @click="schedule(true)"
        >
          <template #icon><ScanOutlined /></template>
        </a-button>
        <a-button
          type="text"
          :title="
            t(
              isFullscreen
                ? 'router.traffic.exitFullscreen'
                : 'router.traffic.fullscreen',
            )
          "
          :aria-label="
            t(
              isFullscreen
                ? 'router.traffic.exitFullscreen'
                : 'router.traffic.fullscreen',
            )
          "
          @click="toggleFullscreen"
        >
          <template #icon>
            <FullscreenExitOutlined v-if="isFullscreen" />
            <FullscreenOutlined v-else />
          </template>
        </a-button>
      </div>
    </div>
    <div
      ref="container"
      class="traffic-canvas"
      role="img"
      :aria-label="`${t('router.traffic.topology')} · ${mode === 'tokens' ? 'Token' : 'Request'}`"
      :aria-busy="rendering"
    />
    <div v-if="graphError" class="graph-error" role="alert">
      <span>{{ t("router.traffic.graphError") }}</span>
      <a-button @click="retry">{{ t("common.retry") }}</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  FullscreenOutlined,
  FullscreenExitOutlined,
  ScanOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from "@ant-design/icons-vue";
import { Graph } from "@antv/g6";
import type { GraphData } from "@antv/g6";
import { nodeFlow, trafficLineWidth } from "./type";
import type { TrafficMode, TrafficSnapshot } from "./type";

const props = defineProps<{
  snapshot: TrafficSnapshot;
  mode: TrafficMode;
}>();
const { t, te, locale } = useI18n();
const container = ref<HTMLDivElement>();
const wrapper = ref<HTMLDivElement>();
const showLabels = ref(true);
const isFullscreen = ref(false);
const rendering = ref(false);
const graphError = ref(false);
let graph: Graph | undefined;
let resizeObserver: ResizeObserver | undefined;
let themeObserver: MutationObserver | undefined;
let disposed = false;
let pending = false;
let shouldFit = true;
const fitZoomScale = (mode: TrafficMode) => (mode === "requests" ? 0.85 : 0.9);

const compact = (value: number) =>
  new Intl.NumberFormat(locale.value.replace("_", "-"), {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

function buildData(): GraphData {
  const { snapshot, mode } = props;
  const stages = [...new Set(snapshot.nodes.map((node) => node.stage))].sort(
    (left, right) => left - right,
  );
  const groups = stages.map((stage) =>
    snapshot.nodes.filter((node) => node.stage === stage),
  );
  const nodeById = new Map(snapshot.nodes.map((node) => [node.id, node]));
  const nodeSize = (): [number, number] => [196, 100];
  const rowCount = Math.max(1, ...groups.map((group) => group.length));
  const positions = new Map<string, { x: number; y: number }>();
  groups.forEach((group, stageIndex) =>
    group.forEach((node, nodeIndex) => {
      positions.set(node.id, {
        x: 120 + stageIndex * 290,
        y: 100 + ((rowCount - group.length) / 2 + nodeIndex) * 180,
      });
    }),
  );
  const style = getComputedStyle(container.value!);
  const fill = style.backgroundColor;
  const text = style.color;
  const themeColor = (name: string) =>
    style.getPropertyValue(name).trim() || text;
  const parseColor = (color: string) => {
    const hex = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color);
    if (hex) return hex.slice(1).map((channel) => parseInt(channel, 16));
    const rgb = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i.exec(
      color,
    );
    return rgb ? rgb.slice(1).map(Number) : undefined;
  };
  const mixColor = (color: string, target: string, amount: number) => {
    const channels = parseColor(color);
    const targetChannels = parseColor(target);
    if (!channels || !targetChannels) return color;
    return `#${channels
      .map((channel, index) =>
        Math.round(channel + (targetChannels[index] - channel) * amount)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")}`;
  };
  const shadeColor = (color: string, amount: number) =>
    mixColor(color, amount > 0 ? "#ffffff" : "#000000", Math.abs(amount));
  const fillChannels = parseColor(fill);
  const isDarkSurface = fillChannels
    ? fillChannels[0] * 0.299 +
        fillChannels[1] * 0.587 +
        fillChannels[2] * 0.114 <
      128
    : false;
  const sourcePalette = [
    "--traffic-source-1",
    "--traffic-source-2",
    "--traffic-source-3",
  ].map(themeColor);
  const providerPalette = [
    themeColor("--color-multicolored-1"),
    themeColor("--color-multicolored-2"),
    themeColor("--color-multicolored-4"),
    themeColor("--color-multicolored-5"),
    themeColor("--traffic-provider-accent"),
  ];
  const createRouteColors = (kind: string, palette: string[]) =>
    new Map(
      snapshot.nodes
        .filter((node) => node.kind === kind)
        .map((node, index) => [node.id, palette[index % palette.length]]),
    );
  const sourceColors = createRouteColors("source", sourcePalette);
  const providerColors = createRouteColors("provider", providerPalette);
  const downstream = new Map<string, string[]>();
  snapshot.edges.forEach((edge) => {
    const targets = downstream.get(edge.source) || [];
    targets.push(edge.target);
    downstream.set(edge.source, targets);
  });
  const routeProviders = new Map<string, string[]>();
  const findProviders = (nodeId: string) => {
    const cached = routeProviders.get(nodeId);
    if (cached) return cached;
    const visited = new Set<string>();
    const providers = new Set<string>();
    const pendingNodes = [nodeId];
    while (pendingNodes.length) {
      const currentId = pendingNodes.pop()!;
      if (visited.has(currentId)) continue;
      visited.add(currentId);
      const node = nodeById.get(currentId);
      if (!node || node.kind === "router") continue;
      if (node.kind === "provider") {
        providers.add(currentId);
      } else {
        pendingNodes.push(...(downstream.get(currentId) || []));
      }
    }
    const result = [...providerColors.keys()].filter((id) => providers.has(id));
    routeProviders.set(nodeId, result);
    return result;
  };
  const routeEdges = snapshot.edges.map((edge) => ({
    ...edge,
    providerId: findProviders(edge.target)[0],
  }));
  const nodeColor = (node: TrafficSnapshot["nodes"][number]) => {
    if (node.kind === "source") return sourceColors.get(node.id) || text;
    if (node.kind === "merge") return themeColor("--color-primary-tip");
    if (node.kind === "router") return themeColor("--color-primary");
    if (node.role === "token-compressor") return themeColor("--color-success");
    if (node.kind === "plugin") return themeColor("--color-warning-strong");
    if (node.kind === "provider") return providerColors.get(node.id) || text;
    return themeColor("--font-tip-color");
  };
  const maximum = Math.max(0, ...snapshot.edges.map((edge) => edge[mode]));
  return {
    nodes: snapshot.nodes.map((node) => {
      const flow = nodeFlow(snapshot, node.id, mode);
      const color = nodeColor(node);
      const isRouter = node.kind === "router";
      const surfaceHighlight = mixColor(
        fill,
        "#ffffff",
        isDarkSurface ? 0.12 : 0.68,
      );
      const surfaceColor = mixColor(fill, color, isDarkSurface ? 0.28 : 0.16);
      const surfaceDepth = mixColor(fill, color, isDarkSurface ? 0.42 : 0.26);
      const materialFill = isRouter
        ? `linear-gradient(145deg, ${shadeColor(color, 0.38)} 0%, ${shadeColor(color, 0.12)} 28%, ${color} 58%, ${shadeColor(color, -0.24)} 100%)`
        : `linear-gradient(145deg, ${surfaceHighlight} 0%, ${surfaceColor} 46%, ${surfaceDepth} 100%)`;
      const incoming = routeEdges
        .filter((edge) => edge.target === node.id)
        .sort(
          (left, right) =>
            positions.get(nodeById.get(left.source)!.id)!.y -
            positions.get(nodeById.get(right.source)!.id)!.y,
        );
      const outgoing = routeEdges
        .filter((edge) => edge.source === node.id)
        .sort(
          (left, right) =>
            positions.get(left.target)!.y - positions.get(right.target)!.y,
        );
      const kind = te(`router.traffic.${node.kind}`)
        ? t(`router.traffic.${node.kind}`)
        : node.kind;
      const value = flow.hasIncoming ? flow.incoming : flow.outgoing;
      const metric =
        mode === "tokens" && node.role === "token-compressor"
          ? `${compact(flow.incoming)} → ${compact(flow.outgoing)}`
          : compact(value);
      return {
        id: node.id,
        style: {
          ...positions.get(node.id),
          size: nodeSize(),
          radius: 8,
          fill: materialFill,
          stroke: color,
          lineWidth: isRouter ? 1.8 : 1.6,
          halo: true,
          haloStroke: color,
          haloLineWidth: isRouter ? 10 : 6,
          haloStrokeOpacity: isRouter
            ? isDarkSurface
              ? 0.14
              : 0.07
            : isDarkSurface
              ? 0.08
              : 0.035,
          shadowColor: isRouter ? themeColor("--bg-primary-shadow") : color,
          shadowBlur: isRouter ? 14 : 8,
          shadowOpacity: isRouter ? 0.2 : isDarkSurface ? 0.12 : 0.07,
          shadowOffsetY: isRouter ? 3 : 2,
          labelText: node.label,
          labelPlacement: "center",
          labelFill: isRouter ? themeColor("--color-white") : text,
          labelFontSize: node.role === "token-compressor" ? 12 : 14,
          labelFontWeight: 650,
          labelLineHeight: 20,
          labelWordWrap: true,
          labelMaxWidth: node.role === "token-compressor" ? 136 : 178,
          labelMaxLines: 2,
          badge: true,
          badges: [
            {
              text: kind,
              placement: "top",
              fill: themeColor("--color-white"),
              backgroundFill: color,
              backgroundStroke: shadeColor(color, -0.18),
              backgroundLineWidth: 0.8,
              backgroundRadius: 6,
              backgroundShadowColor: color,
              backgroundShadowBlur: 2,
              backgroundShadowOpacity: isDarkSurface ? 0.18 : 0.09,
              backgroundShadowOffsetY: 1,
              fontSize: 11,
              padding: [3, 8],
            },
            {
              text: metric,
              placement: "bottom",
              fill: isRouter
                ? themeColor("--color-white")
                : isDarkSurface
                  ? shadeColor(color, 0.64)
                  : shadeColor(color, -0.28),
              backgroundFill: isRouter
                ? shadeColor(color, -0.16)
                : mixColor(fill, color, isDarkSurface ? 0.34 : 0.12),
              backgroundStroke: color,
              backgroundLineWidth: 0.8,
              backgroundRadius: 7,
              backgroundShadowColor: color,
              backgroundShadowBlur: 2,
              backgroundShadowOpacity: isDarkSurface ? 0.14 : 0.07,
              backgroundShadowOffsetY: 1,
              fontSize: 11,
              fontWeight: 700,
              padding: [3, 9],
            },
          ],
          port: true,
          portR: 4,
          portLinkToCenter: true,
          portFill: color,
          portStroke: mixColor(fill, "#ffffff", isDarkSurface ? 0.62 : 0.9),
          portLineWidth: 1.4,
          portShadowColor: color,
          portShadowBlur: 2,
          portShadowOpacity: isDarkSurface ? 0.25 : 0.12,
          ports: [
            ...incoming.map((edge, index) => ({
              key: edge.id,
              placement: [0, (index + 1) / (incoming.length + 1)] as [
                number,
                number,
              ],
            })),
            ...outgoing.map((edge, index) => ({
              key: edge.id,
              placement: [1, (index + 1) / (outgoing.length + 1)] as [
                number,
                number,
              ],
            })),
          ],
        },
      };
    }),
    edges: routeEdges.map((edge) => {
      const source = nodeById.get(edge.source)!;
      const target = nodeById.get(edge.target)!;
      const color =
        target.role === "token-compressor"
          ? nodeColor(target)
          : edge.providerId
            ? providerColors.get(edge.providerId)!
            : nodeColor(source);
      const width = trafficLineWidth(edge[mode], maximum);
      const raised = edge[mode] > 0 && width >= 3;
      const rimColor = shadeColor(color, -0.14);
      const highlightColor = shadeColor(color, 0.68);
      const softHighlightColor = shadeColor(color, 0.32);
      const labelSurface = mixColor(fill, color, isDarkSurface ? 0.24 : 0.09);
      const labelBorder = mixColor(fill, color, isDarkSurface ? 0.56 : 0.32);
      return {
        ...edge,
        type: "cubic-horizontal",
        style: {
          sourcePort: edge.id,
          targetPort: edge.id,
          stroke: raised
            ? `linear-gradient(0deg, ${rimColor} 0%, ${color} 18%, ${softHighlightColor} 38%, ${highlightColor} 50%, ${softHighlightColor} 62%, ${color} 82%, ${rimColor} 100%)`
            : color,
          lineWidth: raised ? width * 0.8 : width,
          strokeOpacity: edge[mode] > 0 ? 0.95 : 0.68,
          halo: raised,
          haloStroke: rimColor,
          haloLineWidth: width,
          haloStrokeOpacity: 0.58,
          haloShadowColor: themeColor("--bg-box-shadow"),
          haloShadowBlur: 3,
          haloShadowOffsetY: 1.5,
          lineDash: edge[mode] === 0 ? [4, 5] : undefined,
          lineCap: "round",
          endArrow: true,
          endArrowSize: 7,
          endArrowFill: color,
          endArrowStroke: color,
          label: showLabels.value,
          labelText: compact(edge[mode]),
          labelFontSize: 10,
          labelFontWeight: 700,
          labelFill: isDarkSurface
            ? shadeColor(color, 0.66)
            : shadeColor(color, -0.34),
          labelBackground: true,
          labelBackgroundFill: labelSurface,
          labelBackgroundStroke: labelBorder,
          labelBackgroundLineWidth: 0.8,
          labelBackgroundOpacity: 0.96,
          labelBackgroundShadowColor: color,
          labelBackgroundShadowBlur: 3,
          labelBackgroundShadowOpacity: isDarkSurface ? 0.22 : 0.1,
          labelBackgroundShadowOffsetY: 1,
          labelPadding: [2, 5],
          labelBackgroundRadius: 6,
          labelAutoRotate: false,
          labelPlacement: "center",
          labelOffsetY: -17,
          increasedLineWidthForHitTesting: 12,
        },
      };
    }),
  };
}

function initialize() {
  if (!container.value || disposed) return;
  graph = new Graph({
    container: container.value,
    width: container.value.clientWidth,
    height: container.value.clientHeight,
    padding: [36, 28, 36, 28],
    animation: false,
    zoomRange: [0.08, 3],
    node: { type: "rect" },
    behaviors: ["drag-canvas"],
  });
}

async function schedule(fit = false) {
  pending = true;
  shouldFit ||= fit;
  if (rendering.value || disposed || !graph) return;
  rendering.value = true;
  try {
    while (pending && !disposed && graph) {
      pending = false;
      graph.setSize(
        container.value!.clientWidth,
        container.value!.clientHeight,
      );
      graph.setData(buildData());
      await graph.render();
      if (shouldFit && !disposed) {
        shouldFit = false;
        await graph.fitView({ when: "always" }, false);
        await graph.zoomBy(fitZoomScale(props.mode), false);
      }
    }
    graphError.value = false;
  } catch {
    if (!disposed) graphError.value = true;
  } finally {
    rendering.value = false;
    if (disposed) graph?.destroy();
  }
}

function retry() {
  if (rendering.value) return;
  graph?.destroy();
  initialize();
  void schedule(true);
}

async function zoom(ratio: number) {
  if (!graph || rendering.value || graphError.value) return;
  try {
    await graph.zoomBy(ratio, false);
  } catch {
    graphError.value = true;
  }
}

async function toggleFullscreen() {
  if (!wrapper.value) return;
  try {
    if (document.fullscreenElement === wrapper.value) {
      await document.exitFullscreen();
    } else {
      await wrapper.value.requestFullscreen();
    }
  } catch {
    isFullscreen.value = false;
  }
}

function handleFullscreenChange() {
  isFullscreen.value = document.fullscreenElement === wrapper.value;
  if (isFullscreen.value) void schedule(true);
}

watch(
  () => props.snapshot,
  () => {
    void schedule(true);
  },
);
watch([() => props.mode, showLabels, locale], () => {
  void schedule();
});

onMounted(() => {
  try {
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    initialize();
    resizeObserver = new ResizeObserver(() => {
      void schedule(true);
    });
    resizeObserver.observe(container.value!);
    themeObserver = new MutationObserver(() => {
      void schedule();
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "style", "data-theme"],
    });
    themeObserver.observe(document.body, {
      attributes: true,
      attributeFilter: ["class", "style", "data-theme"],
    });
    void schedule(true);
  } catch {
    graphError.value = true;
  }
});

onBeforeUnmount(() => {
  disposed = true;
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
  resizeObserver?.disconnect();
  themeObserver?.disconnect();
  if (!rendering.value) graph?.destroy();
});
</script>

<style scoped lang="less">
.traffic-graph-wrap {
  position: relative;
  min-width: 0;
}
.traffic-graph-stage {
  min-width: 0;
}
.traffic-graph-wrap:fullscreen {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: 100vw;
  height: 100vh;
  padding: 16px;
  background: var(--surface-panel-bg-strong);
}
.traffic-graph-wrap:fullscreen .traffic-canvas {
  flex: 1;
  height: auto;
  min-height: 0;
}
.graph-toolbar,
.graph-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.graph-toolbar {
  justify-content: space-between;
  padding: 6px 0;
  border-top: 1px solid var(--border-main-color);
  border-bottom: 1px solid var(--border-main-color);
}
.graph-toolbar > span {
  font-size: 12px;
  font-weight: 600;
}
.graph-actions {
  gap: 4px;
}
.graph-actions :deep(.ant-checkbox-wrapper) {
  margin-right: 12px;
}
.graph-actions :deep(.ant-btn) {
  width: 32px;
  height: 32px;
  padding: 0;
}
.traffic-canvas {
  width: 100%;
  height: 520px;
  min-height: 400px;
  color: var(--font-main-color);
  background-color: var(--surface-panel-bg-strong);
  touch-action: none;
  overflow: hidden;
}
.graph-error {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  background: var(--surface-panel-bg-strong);
  color: var(--font-text-color);
}
@media (max-width: 760px) {
  .traffic-canvas {
    height: 440px;
  }
}
</style>
