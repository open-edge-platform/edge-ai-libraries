<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <section
    ref="panel"
    class="graph-container"
    :class="{ 'graph-fullscreen': fullscreen }"
  >
    <header class="graph-header">
      <h3
        :title="
          $t(trace ? 'console.graphTraceMode' : 'console.graphBrowseMode')
        "
      >
        {{ $t("console.graph") }}
      </h3>
      <div class="graph-actions">
        <a-popover
          v-model:open="sourceOpen"
          trigger="click"
          placement="bottomRight"
          :get-popup-container="popupContainer"
        >
          <template #content>
            <div class="graph-source-menu">
              <label>{{ $t("console.graphPool") }}</label>
              <a-select
                :value="poolId || undefined"
                :placeholder="$t('console.pleaseSelect')"
                :aria-label="$t('console.graphPool')"
                :disabled="!graphPools.length"
                show-search
                option-filter-prop="label"
                :get-popup-container="popupContainer"
                :options="
                  graphPools.map((pool) => ({
                    value: pool.id,
                    label: pool.name || pool.id,
                  }))
                "
                @change="handlePoolChange"
              />
            </div>
          </template>
          <button
            type="button"
            class="graph-source-trigger"
            :class="{ active: sourceOpen }"
            :aria-label="$t('console.graphPool')"
            :aria-expanded="sourceOpen"
            aria-haspopup="dialog"
            @keydown.esc="handleSourceClose"
          >
            <FilterOutlined />
            <span>{{ $t("console.graphPool") }}</span>
            <span v-if="poolName" class="graph-source-name" :title="poolName">{{
              poolName
            }}</span>
            <DownOutlined />
          </button>
        </a-popover>
        <a-popover
          v-model:open="searchOpen"
          trigger="click"
          placement="bottomRight"
          :get-popup-container="popupContainer"
        >
          <template #content>
            <div class="graph-search-menu">
              <a-input-search
                v-model:value="searchName"
                allowClear
                size="small"
                :aria-label="$t('console.findConcept')"
                :placeholder="$t('console.findConcept')"
                @search="handleSearch"
              />
              <span v-if="searchName.trim()">{{
                $t("console.graphMatches", { count: matches.length })
              }}</span>
            </div>
          </template>
          <a-button
            class="icon-button"
            :class="{ active: searchName.trim() }"
            :aria-label="$t('console.findConcept')"
            :title="$t('console.findConcept')"
          >
            <SearchOutlined />
          </a-button>
        </a-popover>
        <a-tooltip
          :title="$t('console.fit')"
          :get-popup-container="popupContainer"
        >
          <a-button
            class="icon-button"
            :aria-label="$t('console.fit')"
            :disabled="!model.nodes.length"
            @click="handleFit"
          >
            <FullscreenOutlined />
          </a-button>
        </a-tooltip>
        <a-tooltip
          :title="
            $t(fullscreen ? 'console.exitFullscreen' : 'console.fullscreen')
          "
          :get-popup-container="popupContainer"
        >
          <a-button
            class="icon-button"
            :aria-label="
              $t(fullscreen ? 'console.exitFullscreen' : 'console.fullscreen')
            "
            @click="handleToggleFullscreen"
          >
            <FullscreenExitOutlined v-if="fullscreen" /><ExpandOutlined
              v-else
            />
          </a-button>
        </a-tooltip>
        <a-tooltip
          :title="$t('console.reload')"
          :get-popup-container="popupContainer"
        >
          <a-button
            class="icon-button"
            :aria-label="$t('console.reload')"
            :loading="loading"
            :disabled="!poolId"
            @click="handleRefresh"
          >
            <ReloadOutlined />
          </a-button>
        </a-tooltip>
      </div>
    </header>
    <div
      class="progress-track"
      :class="{
        searching: loading || retrieving || !traceComplete,
        complete: !!trace && traceComplete && !retrieving,
      }"
      aria-hidden="true"
    >
      <span />
    </div>
    <div class="graph-scroll">
      <a-alert
        v-if="errorMessage"
        type="error"
        showIcon
        :message="errorMessage"
        class="notice-wrap"
      />
      <a-alert
        v-if="graphData?.truncated"
        type="info"
        showIcon
        :message="
          $t('console.graphTruncated', {
            count: graphData.nodes.length,
            total: graphData.total,
          })
        "
        class="notice-wrap"
      />
      <div class="graph-stage">
        <span class="graph-count"
          >{{ model.nodes.length }} {{ $t("console.concepts") }} ·
          {{ model.edges.length }} {{ $t("console.relations") }}</span
        >
        <div
          ref="canvas"
          class="graph-canvas"
          :aria-label="$t('console.graph')"
        />
        <div v-if="!model.nodes.length && !loading" class="graph-empty">
          <a-empty
            :description="
              $t(
                !poolId
                  ? 'console.noGraph'
                  : errorMessage
                    ? 'console.graphLoadFailed'
                    : traversedOnly
                      ? 'console.graphNoTraversal'
                      : 'console.graphEmpty',
              )
            "
          />
        </div>
        <div class="graph-footer">
          <div
            v-if="trace"
            class="legend-wrap"
            :aria-label="$t('console.graphLegend')"
          >
            <template v-if="trace">
              <span v-if="hasSeed"
                ><i :style="legendStyle(0)" />{{ $t("console.seed") }}</span
              >
              <span v-for="hop in hops" :key="hop">
                <i :style="legendStyle(hop)" />
                {{ $t("console.graphHop", { hop }) }}
              </span>
              <span
                :title="$t('console.graphRecallHitHint')"
                ><i class="evidence-dot" />{{
                  $t("console.graphRecallHit")
                }}</span
              >
              <span :title="$t('console.graphFinalResultHint')">
                <i class="final-result-ring" />
                {{ $t("console.graphFinalResult") }}
              </span>
            </template>
          </div>
          <div class="display-controls">
            <label
              ><a-switch v-model:checked="showRelations" size="small" />{{
                $t("console.showRelations")
              }}</label
            >
            <label
              ><a-switch
                v-model:checked="traversedOnly"
                size="small"
                :disabled="!trace"
              />{{ $t("console.traversedOnly") }}</label
            >
            <a-tooltip
              :title="$t('console.graphInteractionHint')"
              :get-popup-container="popupContainer"
            >
              <InfoCircleOutlined
                tabindex="0"
                :aria-label="$t('console.graphInteractionHint')"
              />
            </a-tooltip>
          </div>
        </div>
      </div>
    </div>
    <GraphDetailDrawer
      v-if="detailDrawer.visible"
      :drawer-data="detailDrawer.data"
      @close="handleDetailClose"
    />
  </section>
</template>
<script lang="ts" setup name="ConceptGraph">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { isAxiosError } from "axios";
import { Graph, Tooltip, Arrow, Util, registerNode } from "@antv/g6";
import type { EdgeConfig, NodeConfig, IGroup, ModelConfig } from "@antv/g6";
import {
  ExpandOutlined,
  DownOutlined,
  FilterOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  ReloadOutlined,
  SearchOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons-vue";
import { getAssetPoolGraph } from "@/api/console";
import type { Library, PoolGraph, RetrieveResult } from "@/api/console/type";
import { themeAppStore } from "@/store/theme";
import type { ConceptFocus, GraphDetailData } from "../Type";
import { buildConceptGraph, conceptChunks } from "../ConceptGraphModel";
import GraphDetailDrawer from "./GraphDetailDrawer.vue";
import {
  formatGraphLabel,
  formatGraphScore,
  graphLayerVariables,
  graphLayout,
  graphNodeSize,
  radialGraphFill,
  softGraphEdge,
} from "../ConceptGraphPresentation";

const updateScoreShape = (
  model: ModelConfig | undefined,
  group: IGroup | undefined,
) => {
  if (!group) return;
  const shape = group.find((child) => child.get("name") === "node-score");
  if (typeof model?.score !== "number" || !Number.isFinite(model.score)) {
    shape?.hide();
    return;
  }
  const attributes = {
    x: 0,
    y: String(model.label || "").includes("\n") ? 13 : 9,
    text: formatGraphScore(model.score),
    fill: getComputedStyle(document.body)
      .getPropertyValue("--graph-score-text")
      .trim(),
    fontSize: 9,
    fontWeight: 400,
    textAlign: "center" as const,
    textBaseline: "middle" as const,
  };
  if (shape) {
    shape.attr(attributes);
    shape.show();
  } else group.addShape("text", { attrs: attributes, name: "node-score" });
};
const updateFinalResultRing = (
  model: ModelConfig | undefined,
  group: IGroup | undefined,
) => {
  if (!group) return;
  const shape = group.find((child) => child.get("name") === "final-result-ring");
  if (!model?.finalResult) {
    shape?.hide();
    return;
  }
  const size = Array.isArray(model.size) ? model.size[0] : model.size;
  const attributes = {
    x: 0,
    y: 0,
    r: (typeof size === "number" ? size : 72) / 2 - 1.5,
    stroke: getComputedStyle(document.body)
      .getPropertyValue("--graph-final-result-stroke")
      .trim(),
    lineWidth: 3,
    fill: "transparent",
  };
  if (shape) {
    shape.attr(attributes);
    shape.show();
  } else group.addShape("circle", {
    attrs: attributes,
    name: "final-result-ring",
    capture: false,
  });
};
registerNode(
  "concept-score-circle",
  {
    afterDraw(model, group) {
      updateScoreShape(model, group);
      updateFinalResultRing(model, group);
    },
    afterUpdate(model, item) {
      updateScoreShape(model, item?.getContainer());
      updateFinalResultRing(model, item?.getContainer());
    },
  },
  "circle",
);

const props = defineProps<{
  libraryData: Library;
  result?: RetrieveResult;
  focus?: ConceptFocus;
  retrieving?: boolean;
}>();
const themeStore = themeAppStore();
const panel = ref<HTMLElement>();
const sourceOpen = ref(false);
const searchOpen = ref(false);
const popupContainer = (trigger: HTMLElement) => panel.value || trigger;
const canvas = ref<HTMLElement>();
const loading = ref(false);
const errorMessage = ref("");
const poolId = ref("");
const searchName = ref("");
const traversedOnly = ref(false);
const showRelations = ref(false);
const fullscreen = ref(false);
const graphData = ref<PoolGraph>();
const selectedId = ref("");
const selectedEdgeId = ref("");
const revealedHop = ref(-1);
const traceComplete = ref(true);
const themeColor = (variable: string) =>
  getComputedStyle(panel.value || document.body)
    .getPropertyValue(variable)
    .trim();
const layerColor = (hop: number) => {
  const variables = graphLayerVariables(hop);
  return {
    fill: themeColor(variables.fill),
    stroke: themeColor(variables.stroke),
  };
};
const legendStyle = (hop: number) => {
  const variables = graphLayerVariables(hop);
  return {
    background: `var(${variables.fill})`,
    boxShadow: `0 0 0 2px color-mix(in srgb, var(${variables.stroke}) 22%, transparent)`,
  };
};
const graphPools = computed(() =>
  props.libraryData.asset_pools.filter(
    (pool) =>
      props.result?.graph_traces?.some(
        (trace) => trace.asset_pool_id === pool.id,
      ) ||
      pool.source_statuses.some((status) =>
        props.libraryData.sources.some(
          (source) => source.id === status.source_id && source.type === "graph",
        ),
      ),
  ),
);
const poolName = computed(
  () =>
    graphPools.value.find((pool) => pool.id === poolId.value)?.name ||
    poolId.value,
);
const trace = computed(() =>
  props.result?.graph_traces?.find(
    (item) => item.asset_pool_id === poolId.value,
  ),
);
const model = computed(() =>
  buildConceptGraph(
    graphData.value,
    trace.value,
    props.result,
    traversedOnly.value,
  ),
);
const detailDrawer = computed(() => {
  const node = model.value.nodes.find((node) => node.id === selectedId.value);
  const concept = trace.value?.concepts.find((node) => node.id === selectedId.value);
  const edge = model.value.edges.find((edge) => edge.id === selectedEdgeId.value);
  const data: GraphDetailData = {
    node,
    concept,
    edge,
    sourceName: edge ? nodeName(edge.source) : undefined,
    targetName: edge ? nodeName(edge.target) : undefined,
    citations: conceptChunks(props.result, concept?.hit_chunk_ids || []),
  };
  return { visible: !!selectedId.value || !!selectedEdgeId.value, data };
});
const hops = computed(() =>
  [
    ...new Set(
      model.value.nodes
        .filter((node) => node.concept && node.concept.hop > 0 && !node.seed)
        .map((node) => node.concept!.hop),
    ),
  ].sort((a, b) => a - b),
);
const hasSeed = computed(() =>
  model.value.nodes.some((node) => node.seed || node.concept?.hop === 0),
);
const matches = computed(() => {
  const query = searchName.value.trim().toLowerCase();
  return query
    ? model.value.nodes.filter((node) =>
        `${node.title} ${node.id} ${node.label}`.toLowerCase().includes(query),
      )
    : [];
});
const nodeName = (id: string) =>
  model.value.nodes.find((node) => node.id === id)?.title || id;
let graph: Graph | undefined;
let observer: ResizeObserver | undefined;
let sequence = 0;
let disposed = false;
let traceSequence = 0;
let traceTimer: ReturnType<typeof setTimeout> | undefined;
let resumeTrace: (() => void) | undefined;
const cancelTrace = () => {
  traceSequence++;
  clearTimeout(traceTimer);
  resumeTrace?.();
  resumeTrace = undefined;
};
let hovered: { type: "node" | "edge"; id: string } | undefined;
const clearSelection = () => {
  selectedId.value = "";
  selectedEdgeId.value = "";
};
const handleSourceClose = () => {
  sourceOpen.value = false;
};
const handlePoolChange = (value: unknown) => {
  poolId.value = String(value);
};
const handleToggleFullscreen = () => {
  fullscreen.value = !fullscreen.value;
};
const handleFit = () => fitGraph();
const handleRefresh = () => queryGraph();
const handleDetailClose = () => clearSelection();
const fitGraph = () => {
  if (
    graph &&
    model.value.nodes.length &&
    canvas.value?.clientWidth &&
    canvas.value.clientHeight
  )
    graph.fitView(42);
};
const queryGraph = async () => {
  const current = ++sequence;
  graphData.value = undefined;
  errorMessage.value = "";
  loading.value = !!poolId.value;
  if (!poolId.value) return;
  try {
    const data = await getAssetPoolGraph(props.libraryData.name, poolId.value);
    if (current === sequence) graphData.value = data;
  } catch (error) {
    if (current === sequence) {
      const detail = isAxiosError(error)
        ? error.response?.data?.detail
        : undefined;
      errorMessage.value = detail
        ? typeof detail === "string"
          ? detail
          : JSON.stringify(detail)
        : error instanceof Error
          ? error.message
          : String(error);
    }
  } finally {
    if (current === sequence) loading.value = false;
  }
};
const nodeStyle = (
  node: (typeof model.value.nodes)[number],
): Partial<NodeConfig> => {
  const active =
    selectedId.value === node.id ||
    matches.value.some((match) => match.id === node.id);
  const hop = node.seed ? 0 : node.concept?.hop;
  const reached = hop !== undefined && hop <= revealedHop.value;
  const recallHit = node.recallHit && traceComplete.value;
  const color = recallHit
    ? {
        fill: themeColor("--graph-result-fill"),
        stroke: themeColor("--graph-result-stroke"),
      }
    : reached
      ? layerColor(hop ?? 0)
      : {
          fill: themeColor("--surface-card-bg"),
          stroke: themeColor("--border-info"),
        };
  const score = traceComplete.value ? node.score : undefined;
  return {
    label: formatGraphLabel(node.title || node.id),
    score,
    finalResult: node.finalResult && traceComplete.value,
    size: graphNodeSize(score, recallHit),
    style: {
      fill: recallHit || reached ? radialGraphFill(color.fill) : color.fill,
      opacity: 1,
      stroke: active
        ? themeColor("--color-primary")
        : recallHit || reached
          ? "transparent"
          : color.stroke,
      lineWidth: active ? 2.4 : recallHit || reached ? 0 : 1.6,
      shadowColor: recallHit
        ? themeColor("--graph-result-shadow")
        : reached
          ? color.stroke
          : "transparent",
      shadowBlur: recallHit ? 18 : reached ? 7 : 0,
    },
    labelCfg: {
      position: "center" as const,
      offset: 0,
      style: {
        fill: themeColor(
          recallHit || reached ? "--font-main-color" : "--font-text-color",
        ),
        fontSize: 8,
        fontWeight: 400,
        textAlign: "center",
      },
    },
  };
};
const refreshAppearance = () => {
  if (!graph) return;
  const focusedEdges = new Set(
    model.value.edges
      .filter((edge) =>
        hovered?.type === "edge"
          ? edge.id === hovered.id
          : hovered?.type === "node" &&
            (edge.source === hovered.id || edge.target === hovered.id),
      )
      .map((edge) => edge.id),
  );
  const focusedNodes = new Set<string>();
  if (hovered?.type === "node") focusedNodes.add(hovered.id);
  for (const edge of model.value.edges)
    if (focusedEdges.has(edge.id)) {
      focusedNodes.add(edge.source);
      focusedNodes.add(edge.target);
    }
  for (const node of model.value.nodes) {
    const item = graph.findById(node.id);
    if (item) {
      graph.updateItem(item, nodeStyle(node));
      item.toFront();
    }
  }
  for (const edge of model.value.edges) {
    const item = graph.findById(edge.id);
    if (!item) continue;
    const focused =
      focusedEdges.has(edge.id) || selectedEdgeId.value === edge.id;
    const target = model.value.nodes.find((node) => node.id === edge.target);
    const source = model.value.nodes.find((node) => node.id === edge.source);
    const targetHop = target?.seed ? 0 : target?.concept?.hop;
    const sourceHop = source?.seed ? 0 : source?.concept?.hop;
    const traversed =
      edge.traversed &&
      (traceComplete.value ||
        Math.max(targetHop ?? 0, sourceHop ?? 0) <= revealedHop.value);
    const color = traversed
      ? softGraphEdge(
          target?.recallHit && traceComplete.value
            ? themeColor("--graph-result-stroke")
            : layerColor(targetHop ?? sourceHop ?? 0).stroke,
        )
      : themeColor(focused ? "--color-primary" : "--graph-background-edge");
    graph.updateItem(item, {
      label:
        (hovered?.type === "edge" && focused) ||
        selectedEdgeId.value === edge.id ||
        (showRelations.value && (!hovered || focused))
          ? edge.relation
          : "",
      labelCfg: {
        autoRotate: false,
        style: {
          fill: themeColor("--font-text-color"),
          fontSize: 10,
          fontWeight: 400,
          background: {
            fill: themeColor("--surface-card-bg"),
            padding: [3, 5, 3, 5],
            radius: 3,
          },
        },
      },
      style: {
        stroke: color,
        opacity: focused ? 1 : hovered ? 0.08 : traversed ? 0.85 : 0.32,
        lineWidth: focused ? 2.4 : traversed ? 1.8 : 1,
        endArrow: { path: Arrow.triangle(5, 6, 0), fill: color },
      },
    });
    if (focused) item.toFront();
  }
  focusedNodes.forEach((id) => graph?.findById(id)?.toFront());
  graph.paint();
};
const clearHover = () => {
  hovered = undefined;
  refreshAppearance();
};
const renderGraph = () => {
  if (disposed || !canvas.value?.clientWidth || !canvas.value.clientHeight)
    return;
  if (!graph) {
    const tooltip = new Tooltip({
      itemTypes: ["node", "edge"],
      getContent: (event) => {
        const content = document.createElement("div");
        content.className = "concept-graph-tooltip";
        content.style.whiteSpace = "pre-wrap";
        const id = event?.item?.getID();
        const edge = model.value.edges.find((item) => item.id === id);
        content.textContent = edge
          ? `${nodeName(edge.source)} → ${edge.relation} → ${nodeName(edge.target)}`
          : nodeName(id || "");
        return content;
      },
    });
    graph = new Graph({
      container: canvas.value,
      width: canvas.value.clientWidth,
      height: canvas.value.clientHeight,
      fitView: false,
      fitViewPadding: 42,
      groupByTypes: false,
      animate: true,
      animateCfg: { duration: 650, easing: "easeCubic" },
      minZoom: 0.02,
      maxZoom: 4,
      modes: { default: ["drag-canvas", "zoom-canvas", "drag-node"] },
      layout: graphLayout,
      defaultNode: { type: "concept-score-circle" },
      defaultEdge: { type: "quadratic", style: { lineAppendWidth: 8 } },
      plugins: [tooltip],
    });
    graph.on("node:click", (event) => {
      if (event.item) {
        selectedId.value = event.item.getID();
        selectedEdgeId.value = "";
      }
    });
    graph.on("edge:click", (event) => {
      if (event.item) {
        selectedEdgeId.value = event.item.getID();
        selectedId.value = "";
      }
    });
    graph.on("canvas:click", clearSelection);
    graph.on("node:mouseenter", (event) => {
      if (event.item) {
        hovered = { type: "node", id: event.item.getID() };
        refreshAppearance();
      }
    });
    graph.on("edge:mouseenter", (event) => {
      if (event.item) {
        hovered = { type: "edge", id: event.item.getID() };
        refreshAppearance();
      }
    });
    graph.on("node:mouseleave", clearHover);
    graph.on("edge:mouseleave", clearHover);
    graph.on("canvas:mouseleave", clearHover);
    graph.on("canvas:dragstart", clearHover);
    graph.on("viewportchange", (event) => {
      if (event.action === "zoom") refreshAppearance();
    });
    graph.on("afterlayout", () => {
      refreshAppearance();
      fitGraph();
    });
  }
  hovered = undefined;
  const nodes: NodeConfig[] = model.value.nodes.map((node) => {
    return {
      id: node.id,
      ...nodeStyle(node),
      layoutSize: Math.max(58, graphNodeSize(node.score, node.recallHit)),
    };
  });
  const edges: EdgeConfig[] = model.value.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
  }));
  Util.processParallelEdges(edges, 20, "quadratic", "line", "loop");
  graph.changeData({ nodes, edges });
  refreshAppearance();
};
const handleSearch = () => {
  if (matches.value[0] && graph) {
    graph.focusItem(matches.value[0].id, true);
    searchOpen.value = false;
  }
};
const renderTrace = async () => {
  cancelTrace();
  const current = traceSequence;
  revealedHop.value = -1;
  traceComplete.value = !trace.value;
  await nextTick();
  if (disposed || current !== traceSequence) return;
  renderGraph();
  if (!trace.value) return;
  const layers = [
    ...new Set(
      model.value.nodes.flatMap((node) =>
        node.seed ? [0] : node.concept ? [node.concept.hop] : [],
      ),
    ),
  ].sort((a, b) => a - b);
  const reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;
  for (const [index, hop] of layers.entries()) {
    if (disposed || current !== traceSequence) return;
    revealedHop.value = hop;
    refreshAppearance();
    if (!reducedMotion && index < layers.length - 1) {
      await new Promise<void>((resolve) => {
        resumeTrace = resolve;
        traceTimer = setTimeout(resolve, 180);
      });
    }
  }
  if (disposed || current !== traceSequence) return;
  resumeTrace = undefined;
  traceComplete.value = true;
  refreshAppearance();
  fitGraph();
};
watch(
  graphPools,
  (pools) => {
    if (!pools.some((pool) => pool.id === poolId.value))
      poolId.value = pools[0]?.id || "";
  },
  { immediate: true },
);
watch(
  () =>
    JSON.stringify([
      props.libraryData.name,
      poolId.value,
      graphPools.value.find((pool) => pool.id === poolId.value)
        ?.source_statuses.filter((status) => props.libraryData.sources.some(
          (source) => source.id === status.source_id && source.type === "graph",
        )).map((status) => [
          status.source_id, status.display_status, status.indexed_revision,
          status.updated_at, status.extraction?.outdated,
          status.extraction?.last?.finished_at,
        ]),
    ]),
  queryGraph,
  { immediate: true },
);
watch(poolId, () => {
  clearSelection();
  sourceOpen.value = false;
  searchName.value = "";
  traversedOnly.value = false;
});
watch(
  () => props.result,
  (result) => {
    if (
      result?.graph_traces?.length &&
      !result.graph_traces.some((item) => item.asset_pool_id === poolId.value)
    )
      poolId.value = result.graph_traces[0].asset_pool_id;
  },
  { immediate: true },
);
watch(
  () => props.focus,
  async (focus) => {
    if (!focus) return;
    poolId.value = focus.pool;
    searchName.value = "";
    traversedOnly.value = false;
    await nextTick();
    selectedId.value = focus.id;
    selectedEdgeId.value = "";
    if (graph?.findById(focus.id)) graph.focusItem(focus.id, true);
  },
  { immediate: true },
);
watch([graphData, trace, () => props.result], renderTrace);
watch(traversedOnly, () => nextTick(renderGraph));
watch([trace, () => props.result], () => {
  if (!trace.value && traversedOnly.value) {
    traversedOnly.value = false;
    return;
  }
  refreshAppearance();
});
watch(
  [
    searchName,
    selectedId,
    selectedEdgeId,
    showRelations,
    () => themeStore.theme,
  ],
  refreshAppearance,
  { flush: "post" },
);
watch(fullscreen, async () => {
  await nextTick();
  resizeGraph();
});
const resizeGraph = () => {
  if (!canvas.value?.clientWidth || !canvas.value.clientHeight) return;
  if (!graph) renderGraph();
  else {
    graph.changeSize(canvas.value.clientWidth, canvas.value.clientHeight);
    fitGraph();
    graph.paint();
  }
};
const handleKey = (event: KeyboardEvent) => {
  if (event.key === "Escape") {
    if (selectedId.value || selectedEdgeId.value) {
      clearSelection();
      return;
    }
    sourceOpen.value = false;
    searchOpen.value = false;
    fullscreen.value = false;
  }
};
onMounted(() => {
  observer = new ResizeObserver(resizeGraph);
  if (canvas.value) observer.observe(canvas.value);
  renderGraph();
  document.addEventListener("keydown", handleKey);
});
onUnmounted(() => {
  disposed = true;
  sequence++;
  cancelTrace();
  observer?.disconnect();
  graph?.destroy();
  document.removeEventListener("keydown", handleKey);
});
</script>
<style scoped lang="less">
.graph-container {
  position: relative;
  display: flex;
  flex-direction: column;
  container-type: inline-size;
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  background: var(--bg-card-color);
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  box-shadow: 0 8px 24px var(--bg-box-shadow);
  min-width: 0;
  isolation: isolate;
  overflow: hidden;
  :deep(.intel-btn) {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
}
.graph-header {
  height: 44px;
  flex: 0 0 44px;
  box-sizing: border-box;
  padding: 6px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  h3 {
    min-width: 0;
    margin: 0;
    color: var(--font-main-color);
    font-size: 13px;
    font-weight: 650;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
.graph-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  :deep(.intel-btn + .intel-btn) {
    margin-left: 0;
  }
}
.graph-source-trigger {
  height: 30px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--border-main-color);
  border-radius: 15px;
  color: var(--font-main-color);
  background: var(--bg-content-color);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  &:hover,
  &.active {
    border-color: var(--color-primary-second);
  }
  &:focus-visible {
    outline: 2px solid var(--color-primary-second);
    outline-offset: 2px;
  }
  > .anticon {
    flex-shrink: 0;
    color: var(--color-primary-second);
  }
}
.graph-source-name {
  min-width: 0;
  padding-left: 7px;
  border-left: 1px solid var(--border-main-color);
  color: var(--font-info-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.graph-source-menu,
.graph-search-menu {
  width: 260px;
  max-width: calc(100vw - 72px);
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12px;
  color: var(--font-info-color);
  :deep(.intel-select) {
    width: 100%;
  }
}
.icon-button {
  width: 30px;
  height: 30px;
  padding: 0;
  justify-content: center;
  &.active {
    color: var(--color-primary-second);
    border-color: var(--color-primary-second);
  }
}
.progress-track {
  position: relative;
  height: 3px;
  flex: 0 0 3px;
  overflow: hidden;
  background: var(--border-main-color);
  span {
    display: block;
    width: 0;
    height: 100%;
    background: var(--color-primary-second);
    transition: width 0.35s ease;
  }
  &.searching span {
    width: 32%;
    animation: graph-progress 1.35s ease-in-out infinite;
  }
  &.complete span {
    width: 100%;
  }
}
@keyframes graph-progress {
  from {
    transform: translateX(-110%);
  }
  to {
    transform: translateX(330%);
  }
}
.graph-count {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 1;
  padding: 3px 7px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--surface-panel-bg) 92%, transparent);
  color: var(--font-info-color);
  font-size: 11px;
  pointer-events: none;
}
.graph-stage {
  position: relative;
  flex: 1 0 440px;
  min-height: 440px;
  background-color: var(--surface-panel-bg);
  background-image: radial-gradient(
    var(--border-info) 0.7px,
    transparent 0.7px
  );
  background-size: 17px 17px;
  overflow: hidden;
}
.graph-scroll {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  > .notice-wrap {
    flex-shrink: 0;
  }
}
.graph-canvas {
  width: 100%;
  height: 100%;
}
.graph-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--bg-card-color);
}
.graph-footer {
  position: absolute;
  inset: auto 12px 12px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  pointer-events: none;
}
.legend-wrap,
.display-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 11px;
}
.legend-wrap {
  max-width: 100%;
  max-height: 100px;
  overflow-y: auto;
  padding: 7px 10px;
  border: 1px solid var(--border-main-color);
  border-radius: 6px;
  background: color-mix(in srgb, var(--bg-card-color) 92%, transparent);
  pointer-events: auto;
  color: var(--font-info-color);
  > span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  i {
    width: 10px;
    height: 10px;
    border-radius: 3px;
  }
  .evidence-dot {
    background: var(--graph-result-fill);
    box-shadow: 0 0 0 2px var(--graph-result-shadow);
  }
  .final-result-ring {
    border: 3px solid var(--graph-final-result-stroke);
    border-radius: 50%;
    background: transparent;
  }
}
.display-controls {
  margin-left: auto;
  padding: 7px 10px;
  border: 1px solid var(--border-main-color);
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg-card-color) 96%, transparent);
  box-shadow: 0 4px 16px var(--bg-box-shadow);
  backdrop-filter: blur(8px);
  pointer-events: auto;
  label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--font-info-color);
    cursor: pointer;
  }
}
.notice-wrap {
  margin: 0 14px 8px;
}
.graph-container.graph-fullscreen {
  position: fixed;
  inset: 16px;
  width: auto;
  height: auto;
  z-index: 1100;
}
@container (max-width: 600px) {
  .graph-source-name {
    display: none;
  }
}
@container (max-width: 360px) {
  .graph-source-trigger > span:not(.anticon) {
    display: none;
  }
  .graph-actions {
    gap: 3px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .progress-track.searching span {
    animation: none;
  }
}
:global(.concept-graph-tooltip) {
  max-width: min(280px, calc(100vw - 32px));
  max-height: 240px;
  overflow: auto;
  overflow-wrap: anywhere;
  padding: 8px 10px;
  border: 1px solid var(--border-main-color);
  border-radius: 6px;
  color: var(--font-main-color);
  background: var(--bg-card-color);
  box-shadow: 0 4px 16px var(--bg-box-shadow);
  font-size: 12px;
}
</style>
