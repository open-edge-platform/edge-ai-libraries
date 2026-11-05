<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="board-container">
    <aside class="inventory-wrap">
      <div class="inventory-heading">
        {{ $t("console.create") }}
        <InfoCircleOutlined :title="$t('console.canvasCreateDragHint')" />
      </div>
      <div class="create-shortcuts">
        <button
          v-for="item in resourceCategoryList"
          :key="item.kind"
          type="button"
          draggable="true"
          :data-create-kind="item.kind"
          :style="{ '--resource-color': item.color }"
          :title="$t('console.canvasCreateDragHint')"
          @dragstart="handleCreateDrag($event, item.kind)"
          @click="handleCreate(item.kind)"
        >
          <span class="shortcut-icon"><component :is="item.createIcon" /></span>
          <span>{{ $t(`console.${item.createLabel}`) }}</span>
        </button>
      </div>
      <a-input-search
        v-model:value="searchName"
        allowClear
        :placeholder="$t('console.searchResources')"
        size="small"
      />
      <div class="inventory-summary">
        <span>{{ $t("console.inventory") }}</span>
        <span>{{ visibleNodes.length }} / {{ nodeList.length }}</span>
      </div>
      <div class="inventory-list">
        <section v-for="group in inventoryGroups" :key="group.kind" class="inventory-group">
          <button
            type="button"
            class="group-title"
            :aria-expanded="!collapsedGroups.includes(group.kind)"
            @click="handleToggleGroup(group.kind)"
          >
            <RightOutlined :rotate="collapsedGroups.includes(group.kind) ? 0 : 90" />
            <component :is="group.icon" :style="{ color: group.color }" />
            <strong>{{ $t(`console.${group.label}`) }}</strong>
            <span>{{ group.matched }} / {{ group.total }}</span>
          </button>
          <template v-if="!collapsedGroups.includes(group.kind)">
              <button
                v-for="node in group.nodes"
                :key="node.key"
                type="button"
                draggable="true"
                class="inventory-item"
                :data-resource="node.key"
                :style="{ '--resource-color': resourceCategories[node.kind].color }"
                :class="{ selected: selectedKey === node.key, placed: !!positions[node.key] }"
                :title="[
                  node.name,
                  node.origin || [node.database, node.collection].filter(Boolean).join(' / ') || node.id,
                  $te(`console.${node.status}`) ? $t(`console.${node.status}`) : node.status,
                  node.error,
                ].filter(Boolean).join('\n')"
                @dragstart="handleInventoryDrag($event, node.key)"
                @click="handleInventoryClick(node.key)"
              >
                <CanvasResource :node="node" compact />
                <span
                  v-if="positions[node.key]"
                  class="placed-indicator"
                  role="img"
                  :aria-label="$t('console.onCanvas')"
                  :title="$t('console.onCanvas')"
                />
                <PlusOutlined v-else />
              </button>
          </template>
        </section>
        <a-empty v-if="!inventoryGroups.some((group) => group.matched)" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
      </div>
      <p class="inventory-hint">
        <InfoCircleOutlined />
        {{ $t("console.canvasDragHint") }}
      </p>
    </aside>
    <div class="board-workspace">
      <div class="board-toolbar">
        <a-space :size="6" align="center" wrap class="toolbar-group">
          <a-button type="default" size="small" :aria-label="$t('console.zoomOut')" @click="handleZoomOut">
            <template #icon><MinusOutlined /></template>
            {{ $t("console.zoomOut") }}
          </a-button>
          <span class="zoom-label">{{ Math.round(zoom * 100) }}%</span>
          <a-button type="default" size="small" :aria-label="$t('console.zoomIn')" @click="handleZoomIn">
            <template #icon><PlusOutlined /></template>
            {{ $t("console.zoomIn") }}
          </a-button>
          <a-tooltip :title="$t('console.fit')">
            <a-button type="default" size="small" :aria-label="$t('console.fit')" @click="handleFit()">
              <template #icon><FullscreenOutlined /></template>
              {{ $t("console.fit") }}
            </a-button>
          </a-tooltip>
        </a-space>
        <a-space :size="6" align="center" wrap class="toolbar-group">
          <a-button type="default" size="small" @click="handlePlaceAll">{{ $t("console.placeAll") }}</a-button>
          <a-button type="default" size="small" @click="handleAutoLayout">
            <template #icon><PartitionOutlined /></template>
            {{ $t("console.autoLayout") }}
          </a-button>
          <a-tooltip :title="$t('console.clearCanvas')">
            <a-button type="default" size="small" :aria-label="$t('console.clearCanvas')" @click="handleClear">
              <template #icon><ClearOutlined /></template>
              {{ $t("console.clearCanvas") }}
            </a-button>
          </a-tooltip>
          <a-popover
            v-model:open="linkControlsOpen"
            trigger="click"
            placement="bottomRight"
            :title="$t('console.manualConnect')"
          >
            <a-button
              type="default"
              size="small"
              class="connect-trigger"
              :aria-label="$t('console.manualConnect')"
              :aria-expanded="linkControlsOpen"
              :title="$t('console.manualConnect')"
            >
              <template #icon><LinkOutlined /></template>
              {{ $t("console.manualConnect") }}
            </a-button>
            <template #content>
              <div class="connection-form">
                <p>{{ $t("console.linkHint") }}</p>
                <div class="connection-field">
                  <span>{{ $t("console.linkFrom") }}</span>
                  <a-select
                    v-model:value="linkFrom"
                    showSearch
                    optionFilterProp="label"
                    :disabled="loading"
                    :aria-label="$t('console.linkFrom')"
                    :placeholder="$t('console.linkFrom')"
                    :options="connectionNodes.map((node) => ({ value: node.key, label: node.name }))"
                  />
                </div>
                <div class="connection-field">
                  <span>{{ $t("console.linkTo") }}</span>
                  <a-select
                    v-model:value="linkTo"
                    showSearch
                    optionFilterProp="label"
                    :disabled="loading"
                    :aria-label="$t('console.linkTo')"
                    :placeholder="$t('console.linkTo')"
                    :options="targetNodes.map((node) => ({ value: node.key, label: node.name }))"
                  />
                </div>
                <a-button
                  type="primary"
                  :loading="loading"
                  :disabled="!linkFrom || !linkTo"
                  @click="handleConnect"
                >{{ $t("console.connect") }}</a-button>
              </div>
            </template>
          </a-popover>
        </a-space>
        <div class="resource-legend" role="list" :aria-label="$t('console.resourceLegend')">
          <span
            v-for="item in resourceCategoryList"
            :key="item.kind"
            class="legend-item"
            role="listitem"
            :style="{ '--resource-color': item.color }"
          >
            <span class="legend-glyph"><component :is="item.icon" /></span>
            <span>{{ $t(`console.${item.label}`) }}</span>
          </span>
        </div>
      </div>
      <div
        ref="viewport"
        class="canvas-viewport"
        :class="{ panning: drag?.mode === 'pan', linking: !!linkPreview }"
        @pointerdown="handleBackgroundPointerDown"
        @wheel="handleWheel"
        @dragover.prevent
        @drop.prevent="handleDrop($event)"
      >
        <div
          class="canvas-sizer"
          :style="{ width: `${stageSize.width * zoom}px`, height: `${stageSize.height * zoom}px` }"
        >
          <div
            class="canvas-stage"
            :style="{ width: `${stageSize.width}px`, height: `${stageSize.height}px`, transform: `scale(${zoom})` }"
          >
            <svg class="canvas-edges" :width="stageSize.width" :height="stageSize.height">
              <defs>
                <marker :id="markerId" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
                </marker>
              </defs>
              <g v-for="edge in visibleEdges" :key="`${edge.from}:${edge.to}`">
                <path
                  :d="getEdgePath(edge)"
                  class="edge-line"
                  :class="{
                    'pool-source': edge.from.startsWith('pool:'),
                    content: edge.content,
                    frozen: edge.frozen,
                    failed: ['failed', 'extraction_failed'].includes(edge.status || ''),
                    pending: edge.status && !['ready', 'failed', 'extraction_failed'].includes(edge.status),
                    selected: selectedEdge?.from === edge.from && selectedEdge?.to === edge.to,
                    related: edge.from === selectedKey || edge.to === selectedKey,
                  }"
                  :marker-end="`url(#${markerId})`"
                />
                <path
                  :d="getEdgePath(edge)"
                  class="edge-hit"
                  role="button"
                  tabindex="0"
                  :aria-label="`${nodeList.find((node) => node.key === edge.from)?.name} → ${nodeList.find((node) => node.key === edge.to)?.name}`"
                  @pointerdown.stop
                  @click.stop="handleSelectEdge(edge)"
                  @keydown.enter="handleSelectEdge(edge)"
                />
              </g>
              <path v-if="linkPreview" :d="previewPath" class="link-preview" />
            </svg>
            <div
              v-for="node in visibleNodes"
              :key="node.key"
              :data-node="node.key"
              class="canvas-node"
              :class="{ 'drop-target': dropTarget === node.key }"
              :style="{ left: `${positions[node.key].x}px`, top: `${positions[node.key].y}px`, width: `${NODE_WIDTH}px`, height: `${NODE_HEIGHT}px`, '--resource-color': resourceCategories[node.kind].color, '--node-port-y': `${NODE_PORT_Y}px` }"
              role="button"
              tabindex="0"
              :aria-label="node.name"
              :title="$t('console.openResourceDetails', { name: node.name })"
              @pointerdown.stop="handleNodePointerDown($event, node.key)"
              @click.stop="handleNodeClick($event, node.key)"
              @keydown.enter.stop="handleSelect(node.key)"
              @keydown.space.prevent.stop="handleSelect(node.key)"
              @dragover.prevent.stop
              @drop.prevent.stop="handleDrop($event, node.key)"
            >
              <CanvasResource :node="node" :selected="selectedKey === node.key" />
              <button
                v-if="node.kind !== 'asset'"
                type="button"
                class="node-port left-port"
                :aria-label="$t('console.linkPort', { name: node.name })"
                @pointerdown.stop.prevent="handlePortPointerDown($event, node.key, 'left')"
                @click.stop
              />
              <button
                v-if="node.kind !== 'source'"
                type="button"
                class="node-port right-port"
                :aria-label="$t('console.linkPort', { name: node.name })"
                @pointerdown.stop.prevent="handlePortPointerDown($event, node.key, 'right')"
                @click.stop
              />
            </div>
          </div>
        </div>
        <div v-if="!visibleNodes.length" class="canvas-empty">
          <a-empty :description="$t('console.canvasHint')" />
          <a-button @click.stop="handlePlaceAll">{{ $t("console.placeAll") }}</a-button>
        </div>
      </div>
    </div>
  </div>
</template>
<script lang="ts" setup name="CanvasBoard">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Empty } from "ant-design-vue";
import {
  ClearOutlined, FullscreenOutlined, InfoCircleOutlined,
  LinkOutlined, MinusOutlined, PartitionOutlined, PlusOutlined,
  RightOutlined,
} from "@ant-design/icons-vue";
import { Local } from "@/utils/storage";
import { customNotification } from "@/utils/notification";
import CanvasResource from "./CanvasResource.vue";
import {
  arrangeCanvasNodes, CANVAS_PADDING, COLUMN_STEP, MAX_AUTO_ASSETS,
  NODE_HEIGHT, NODE_PORT_Y, NODE_WIDTH, ROW_STEP,
} from "../ResourceModel";
import type { CanvasEdge, CanvasNode, NodeKind, Position } from "../Type";
import { resourceCategories, resourceCategoryList } from "../ResourcePresentation";

const props = defineProps<{
  libraryId: string;
  nodeList: CanvasNode[];
  edgeList: CanvasEdge[];
  loading: boolean;
  selectedKey?: string;
  selectedEdge?: CanvasEdge;
}>();
const emit = defineEmits<{
  connect: [from: string, to: string];
  select: [key: string];
  "select-edge": [edge: CanvasEdge];
  files: [data: DataTransfer, target?: CanvasNode, position?: Position];
  create: [kind: NodeKind, position?: Position, target?: CanvasNode];
  deselect: [];
  detach: [];
}>();
const { t } = useI18n();
const handleCreate = (kind: NodeKind) => emit("create", kind);
const handleSelectEdge = (edge: CanvasEdge) => emit("select-edge", edge);
const handleSelect = (key: string) => emit("select", key);
const handleConnect = () => emit("connect", linkFrom.value!, linkTo.value!);
const handleZoomOut = () => setZoom(zoom.value / 1.15);
const handleZoomIn = () => setZoom(zoom.value * 1.15);
const viewport = ref<HTMLElement>();
const searchName = ref("");
const zoom = ref(1);
const viewSize = ref({ width: 0, height: 0 });
const collapsedGroups = ref<NodeKind[]>([]);
const linkFrom = ref<string>();
const linkTo = ref<string>();
const linkControlsOpen = ref(false);
const dropTarget = ref("");
const linkPreview = ref<{ key: string; side: "left" | "right"; to: Position }>();
const markerId = `canvas-arrow-${props.libraryId}`;
const isPosition = (value: unknown): value is Position =>
  value !== null && typeof value === "object" &&
  "x" in value && typeof value.x === "number" && Number.isFinite(value.x) && value.x >= 0 &&
  "y" in value && typeof value.y === "number" && Number.isFinite(value.y) && value.y >= 0;
const readLayout = (): Record<string, Position> | null => {
  try {
    const saved: unknown = Local.get(`console.canvas.${props.libraryId}`);
    if (saved === null) return null;
    if (typeof saved !== "object" || Array.isArray(saved))
      throw new Error(t("console.invalidLayout"));
    const entries = Object.entries(saved);
    if (!entries.every((entry): entry is [string, Position] => isPosition(entry[1])))
      throw new Error(t("console.invalidLayout"));
    return Object.fromEntries(entries);
  } catch (error) {
    customNotification("warning", t("common.prompt"), `${t("console.invalidLayout")} ${error instanceof Error ? error.message : String(error)}`);
    return null;
  }
};
const savedLayout = readLayout();
const positions = ref<Record<string, Position>>(savedLayout || {});
let initialized = savedLayout !== null;
let moved = false;
let resizeObserver: ResizeObserver | undefined;
type DragState =
  | { mode: "move"; key: string; start: Position; origin: Position }
  | { mode: "link"; key: string }
  | { mode: "pan"; start: Position; origin: Position };
const drag = ref<DragState>();
const visibleNodes = computed(() => props.nodeList.filter((node) => positions.value[node.key]));
const visibleKeys = computed(() => new Set(visibleNodes.value.map((node) => node.key)));
const visibleEdges = computed(() => props.edgeList.filter((edge) =>
  visibleKeys.value.has(edge.from) && visibleKeys.value.has(edge.to),
));
const inventoryGroups = computed(() => {
  const query = searchName.value.trim().toLowerCase();
  return resourceCategoryList.map((category) => {
    const all = props.nodeList.filter((node) => node.kind === category.kind);
    const matched = all.filter((node) =>
      [node.name, node.id, node.origin, node.database, node.collection, node.resourceType]
        .some((value) => value?.toLowerCase().includes(query)),
    );
    return {
      ...category, total: all.length, matched: matched.length, nodes: matched,
    };
  });
});
const connectionNodes = computed(() => props.nodeList.filter((node) =>
  !node.content && !(node.kind === "source" && node.resourceType === "object"),
));
const targetNodes = computed(() => {
  const from = props.nodeList.find((node) => node.key === linkFrom.value);
  return connectionNodes.value.filter((node) => !from ||
    (from.kind === "pool" ? node.kind !== "pool" : node.kind === "pool"),
  );
});
const stageSize = computed(() => ({
  width: Math.max(
    viewSize.value.width / zoom.value,
    ...visibleNodes.value.map((node) => positions.value[node.key].x + NODE_WIDTH + CANVAS_PADDING),
    1,
  ),
  height: Math.max(
    viewSize.value.height / zoom.value,
    ...visibleNodes.value.map((node) => positions.value[node.key].y + NODE_HEIGHT + CANVAS_PADDING),
    1,
  ),
}));
const handleToggleGroup = (kind: NodeKind) => {
  collapsedGroups.value = collapsedGroups.value.includes(kind)
    ? collapsedGroups.value.filter((value) => value !== kind)
    : [...collapsedGroups.value, kind];
};
const saveLayout = () => {
  try {
    Local.set(`console.canvas.${props.libraryId}`, positions.value);
  } catch (error) {
    customNotification("error", t("common.error"), `${t("console.layoutSaveFailed")} ${error instanceof Error ? error.message : String(error)}`);
  }
};
const placeNodes = (keys: string[], position?: Position) => {
  initialized = true;
  keys.forEach((key, index) => {
    if (positions.value[key]) return;
    const column = resourceCategoryList.findIndex((category) => key.startsWith(`${category.kind}:`));
    const point = position
      ? { x: position.x, y: position.y + index * ROW_STEP }
      : { x: CANVAS_PADDING + Math.max(0, column) * COLUMN_STEP, y: CANVAS_PADDING };
    while (Object.values(positions.value).some((other) =>
      Math.abs(other.x - point.x) < NODE_WIDTH + 12 &&
      Math.abs(other.y - point.y) < NODE_HEIGHT + 12,
    )) point.y += ROW_STEP;
    positions.value[key] = point;
  });
  saveLayout();
};
const handleFit = async (initial = false) => {
  await nextTick();
  const area = viewport.value;
  if (!area || !visibleNodes.value.length) {
    zoom.value = 1;
    area?.scrollTo(0, 0);
    return;
  }
  const points = visibleNodes.value.map((node) => positions.value[node.key]);
  const minX = Math.max(0, Math.min(...points.map((point) => point.x)) - CANVAS_PADDING);
  const minY = Math.max(0, Math.min(...points.map((point) => point.y)) - CANVAS_PADDING);
  const width = Math.max(...points.map((point) => point.x)) + NODE_WIDTH + CANVAS_PADDING - minX;
  const height = Math.max(...points.map((point) => point.y)) + NODE_HEIGHT + CANVAS_PADDING - minY;
  // Tall graphs should scroll on first load, not shrink their cards to unreadable sizes.
  zoom.value = Math.max(
    initial ? 0.75 : 0.25,
    Math.min(1, area.clientWidth / width, initial ? 1 : area.clientHeight / height),
  );
  await nextTick();
  area.scrollTo(minX * zoom.value, minY * zoom.value);
};
const setZoom = async (value: number, event?: WheelEvent) => {
  const area = viewport.value;
  if (!area) return;
  const rect = area.getBoundingClientRect();
  const anchor = {
    x: event ? event.clientX - rect.left : area.clientWidth / 2,
    y: event ? event.clientY - rect.top : area.clientHeight / 2,
  };
  const before = { x: (area.scrollLeft + anchor.x) / zoom.value, y: (area.scrollTop + anchor.y) / zoom.value };
  zoom.value = Math.max(0.25, Math.min(2, value));
  await nextTick();
  area.scrollTo(before.x * zoom.value - anchor.x, before.y * zoom.value - anchor.y);
};
const handleWheel = (event: WheelEvent) => {
  if (!event.ctrlKey && !event.metaKey) return;
  event.preventDefault();
  setZoom(zoom.value * (event.deltaY < 0 ? 1.1 : 1 / 1.1), event);
};
const handleAutoLayout = () => {
  positions.value = { ...positions.value, ...arrangeCanvasNodes(visibleNodes.value, props.edgeList) };
  saveLayout();
  handleFit();
};
const handlePlaceAll = () => {
  const assets = props.nodeList.filter((node) => node.kind === "asset");
  placeNodes([
    ...props.nodeList.filter((node) => node.kind !== "asset").map((node) => node.key),
    ...assets.slice(0, MAX_AUTO_ASSETS).map((node) => node.key),
  ]);
  if (assets.length > MAX_AUTO_ASSETS)
    customNotification("info", t("common.prompt"), t("console.canvasAssetLimit", { count: MAX_AUTO_ASSETS }));
  handleAutoLayout();
};
const handleClear = () => {
  initialized = true;
  positions.value = {};
  saveLayout();
  emit("deselect");
};
const removeNode = (key: string) => {
  delete positions.value[key];
  saveLayout();
};
const showLinked = (key: string) => {
  placeNodes([key, ...props.edgeList.filter((edge) => edge.from === key || edge.to === key).flatMap((edge) => [edge.from, edge.to])]);
  handleFit();
};
const handleInventoryClick = async (key: string) => {
  placeNodes([key]);
  emit("select", key);
  await nextTick();
  const point = positions.value[key];
  viewport.value?.scrollTo({
    left: Math.max(0, (point.x + NODE_WIDTH / 2) * zoom.value - viewport.value.clientWidth / 2),
    top: Math.max(0, (point.y + NODE_HEIGHT / 2) * zoom.value - viewport.value.clientHeight / 2),
    behavior: "smooth",
  });
};
const portPoint = (key: string, side: "left" | "right"): Position => ({
  x: positions.value[key].x + (side === "right" ? NODE_WIDTH : 0),
  y: positions.value[key].y + NODE_PORT_Y,
});
const curve = (from: Position, to: Position) => {
  const offset = Math.max(40, Math.abs(to.x - from.x) / 2);
  return `M ${from.x} ${from.y} C ${from.x + offset} ${from.y}, ${to.x - offset} ${to.y}, ${to.x} ${to.y}`;
};
const getEdgePath = (edge: CanvasEdge) => curve(portPoint(edge.from, "right"), portPoint(edge.to, "left"));
const previewPath = computed(() => {
  const preview = linkPreview.value;
  if (!preview) return "";
  const point = portPoint(preview.key, preview.side);
  return preview.side === "right" ? curve(point, preview.to) : curve(preview.to, point);
});
const toCanvas = (clientX: number, clientY: number): Position => {
  const area = viewport.value!;
  const rect = area.getBoundingClientRect();
  return { x: (clientX - rect.left + area.scrollLeft) / zoom.value, y: (clientY - rect.top + area.scrollTop) / zoom.value };
};
const handleInventoryDrag = (event: DragEvent, key: string) => {
  event.dataTransfer?.setData("application/x-console-node", key);
};
const handleCreateDrag = (event: DragEvent, kind: NodeKind) => {
  event.dataTransfer?.setData("application/x-console-create", kind);
};
const relatedPosition = (kind: NodeKind, target: CanvasNode | undefined, fallback: Position): Position => {
  const anchor = target && positions.value[target.key];
  if (!anchor || !target || (kind === "pool" ? target.kind === "pool" : target.kind !== "pool"))
    return fallback;
  const offset = kind === "source" || (kind === "pool" && target.kind === "asset") ? COLUMN_STEP : -COLUMN_STEP;
  return { x: Math.max(CANVAS_PADDING, anchor.x + offset), y: anchor.y };
};
const handleDrop = (event: DragEvent, target?: string) => {
  const data = event.dataTransfer;
  if (!data || props.loading) return;
  const point = toCanvas(event.clientX, event.clientY);
  const position = { x: Math.max(0, point.x - NODE_WIDTH / 2), y: Math.max(0, point.y - 20) };
  const targetNode = props.nodeList.find((node) => node.key === target);
  if (Array.from(data.types).includes("Files")) {
    emit("files", data, targetNode, relatedPosition("asset", targetNode, position));
    return;
  }
  const creation = data.getData("application/x-console-create");
  if (creation === "asset" || creation === "pool" || creation === "source") {
    emit("create", creation, relatedPosition(creation, targetNode, position), targetNode);
    return;
  }
  const key = data.getData("application/x-console-node");
  if (!props.nodeList.some((node) => node.key === key)) return;
  if (target && key !== target) {
    const node = props.nodeList.find((value) => value.key === key)!;
    placeNodes([key], relatedPosition(node.kind, targetNode, position));
    emit("connect", key, target);
    return;
  }
  positions.value[key] = position;
  initialized = true;
  saveLayout();
  emit("select", key);
};
const startPointerTracking = () => {
  moved = false;
  window.addEventListener("pointermove", handlePointerMove);
  window.addEventListener("pointerup", handlePointerUp, { once: true });
  window.addEventListener("pointercancel", cancelDrag, { once: true });
};
const stopPointerTracking = () => {
  drag.value = undefined;
  linkPreview.value = undefined;
  dropTarget.value = "";
  window.removeEventListener("pointermove", handlePointerMove);
  window.removeEventListener("pointerup", handlePointerUp);
  window.removeEventListener("pointercancel", cancelDrag);
};
const handleNodePointerDown = (event: PointerEvent, key: string) => {
  if (event.button !== 0 || props.loading) return;
  event.preventDefault();
  drag.value = { mode: "move", key, start: { x: event.clientX, y: event.clientY }, origin: { ...positions.value[key] } };
  startPointerTracking();
};
const handlePortPointerDown = (event: PointerEvent, key: string, side: "left" | "right") => {
  if (event.button !== 0 || props.loading) return;
  drag.value = { mode: "link", key };
  linkPreview.value = { key, side, to: portPoint(key, side) };
  startPointerTracking();
};
const handleBackgroundPointerDown = (event: PointerEvent) => {
  if ((event.button !== 0 && event.button !== 1) || (event.target instanceof Element && event.target.closest(".canvas-empty"))) return;
  event.preventDefault();
  const area = viewport.value!;
  drag.value = { mode: "pan", start: { x: event.clientX, y: event.clientY }, origin: { x: area.scrollLeft, y: area.scrollTop } };
  startPointerTracking();
};
const targetAt = (event: PointerEvent) => {
  const element = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-node]");
  return element && viewport.value?.contains(element) ? element.dataset.node : undefined;
};
const handlePointerMove = (event: PointerEvent) => {
  const state = drag.value;
  if (!state) return;
  if (state.mode === "link") {
    linkPreview.value!.to = toCanvas(event.clientX, event.clientY);
    dropTarget.value = targetAt(event) || "";
    return;
  }
  const dx = event.clientX - state.start.x, dy = event.clientY - state.start.y;
  if (Math.abs(dx) + Math.abs(dy) > 5) moved = true;
  if (!moved) return;
  if (state.mode === "pan") viewport.value?.scrollTo(state.origin.x - dx, state.origin.y - dy);
  else positions.value[state.key] = { x: Math.max(0, state.origin.x + dx / zoom.value), y: Math.max(0, state.origin.y + dy / zoom.value) };
};
const handlePointerUp = (event: PointerEvent) => {
  const state = drag.value;
  if (state?.mode === "link") {
    const target = targetAt(event);
    if (target && target !== state.key) emit("connect", state.key, target);
  } else if (state?.mode === "move" && moved) {
    const point = positions.value[state.key];
    const target = visibleNodes.value.find((node) => {
      const other = positions.value[node.key];
      return node.key !== state.key && point.x + NODE_WIDTH / 2 > other.x &&
        point.x + NODE_WIDTH / 2 < other.x + NODE_WIDTH &&
        point.y + NODE_HEIGHT / 2 > other.y && point.y + NODE_HEIGHT / 2 < other.y + NODE_HEIGHT;
    });
    if (target) {
      positions.value[state.key] = state.origin;
      emit("connect", state.key, target.key);
    }
    saveLayout();
  } else if (state?.mode === "move") emit("select", state.key);
  else if (state?.mode === "pan" && !moved) emit("deselect");
  stopPointerTracking();
};
const cancelDrag = () => {
  if (drag.value?.mode === "move") positions.value[drag.value.key] = drag.value.origin;
  stopPointerTracking();
};
const handleNodeClick = (event: MouseEvent, key: string) => {
  // Assistive clicks have no preceding pointer sequence.
  if (event.detail === 0) emit("select", key);
};
const handleKeydown = (event: KeyboardEvent) => {
  if (props.loading) return;
  const target = event.target instanceof Element ? event.target : undefined;
  if (target?.closest(".intel-modal, .ant-modal")) return;
  if (event.key === "Escape" && linkControlsOpen.value) {
    linkControlsOpen.value = false;
    return;
  }
  if (target?.closest("input, textarea, select, [contenteditable='true'], .connection-form")) return;
  if (event.key === "Escape") {
    cancelDrag();
    emit("deselect");
  }
  if (event.key === "Delete" || event.key === "Backspace") {
    if (props.selectedKey) {
      event.preventDefault();
      removeNode(props.selectedKey);
      emit("deselect");
    } else if (props.selectedEdge) {
      event.preventDefault();
      emit("detach");
    }
  }
};
watch(linkFrom, () => { linkTo.value = undefined; });
watch(() => props.nodeList, (nodes) => {
  if (!initialized && nodes.length) {
    const assets = nodes.filter((node) => node.kind === "asset");
    const initial = nodes.filter((node) => node.kind !== "asset" || assets.length <= 40);
    positions.value = arrangeCanvasNodes(initial, props.edgeList);
    initialized = true;
    saveLayout();
  }
  if (linkFrom.value && !nodes.some((node) => node.key === linkFrom.value)) linkFrom.value = undefined;
  if (linkTo.value && !nodes.some((node) => node.key === linkTo.value)) linkTo.value = undefined;
}, { immediate: true });
onMounted(() => {
  resizeObserver = new ResizeObserver(([entry]) => {
    viewSize.value = { width: entry.contentRect.width, height: entry.contentRect.height };
  });
  if (viewport.value) resizeObserver.observe(viewport.value);
  window.addEventListener("keydown", handleKeydown);
  handleFit(true);
});
onUnmounted(() => {
  stopPointerTracking();
  resizeObserver?.disconnect();
  window.removeEventListener("keydown", handleKeydown);
});
defineExpose({ placeNodes, removeNode, showLinked });
</script>
<style scoped lang="less">
.board-container {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.inventory-wrap {
  width: 224px;
  flex-shrink: 0;
  padding: 14px 12px 0;
  border-right: 1px solid var(--border-main-color);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.inventory-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  color: var(--font-main-color);
  font-size: 13px;
  font-weight: 600;
  > span {
    font-size: 11px;
    color: var(--font-info-color);
    font-weight: 400;
  }
}
.create-shortcuts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 12px;
  flex-shrink: 0;
  button {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 5px 8px;
    border: 1px dashed var(--border-main-color);
    border-radius: 5px;
    background: var(--bg-card-color);
    color: var(--font-text-color);
    cursor: grab;
    font-size: 12px;
    white-space: nowrap;
    text-align: left;
    &:hover {
      border-color: var(--resource-color);
      color: var(--resource-color);
    }
  }
}
.shortcut-icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 5px;
  background: var(--resource-color);
  color: var(--color-white);
  font-size: 14px;
}
.inventory-summary {
  display: flex;
  justify-content: space-between;
  padding: 12px 0 4px;
  flex-shrink: 0;
  color: var(--font-info-color);
  font-size: 11px;
}
.inventory-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin: 0 -4px;
}
.inventory-group {
  margin-bottom: 12px;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 4px;
  border: 0;
  background: transparent;
  color: var(--font-text-color);
  font-size: 12px;
  cursor: pointer;
  strong {
    flex: 1;
    text-align: left;
    font-weight: 500;
  }
  > span:last-child {
    font-size: 10px;
    color: var(--font-info-color);
  }
  > .anticon:first-child {
    font-size: 9px;
  }
}
.inventory-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 7px;
  width: 100%;
  margin-bottom: 3px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: var(--bg-card-color);
  border-color: var(--border-main-color);
  cursor: grab;
  text-align: left;
  .resource-card {
    flex: 1;
  }
  > .anticon:last-child {
    flex-shrink: 0;
    color: var(--font-tip-color);
    font-size: 10px;
  }
  &:hover,
  &.selected {
    border-color: var(--resource-color);
  }
}
.placed-indicator {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
}
.inventory-hint {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  padding: 10px 0;
  margin: 0;
  color: var(--font-info-color);
  font-size: 11px;
  line-height: 1.6;
  border-top: 1px solid var(--border-main-color);
  .anticon {
    margin-top: 3px;
  }
}
.board-workspace {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.board-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  gap: 8px;
  padding: 10px 12px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border-main-color);
  :deep(.intel-space-item) {
    display: flex;
    align-items: center;
  }
  :deep(.intel-btn) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    height: 28px;
    border: 1px solid var(--border-main-color);
    background: var(--bg-content-color);
    white-space: nowrap;
    > .anticon + span {
      margin-inline-start: 0;
    }
    &:hover,
    &:focus-visible {
      border-color: var(--color-primary-second);
    }
  }
}
.toolbar-group {
  min-width: 0;
  max-width: 100%;
}
.zoom-label {
  min-width: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  text-align: center;
  font-size: 11px;
  color: var(--font-info-color);
}
.resource-legend {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 10px;
  margin-left: auto;
  color: var(--font-info-color);
  font-size: 11px;
  white-space: nowrap;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.legend-glyph {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  background: var(--resource-color);
  color: var(--color-white);
  font-size: 10px;
}
.canvas-viewport {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
  background-color: var(--bg-main-color);
  background-image: radial-gradient(var(--border-main-color) 1px, transparent 1px);
  background-size: 18px 18px;
  cursor: grab;
  touch-action: none;
  &.panning {
    cursor: grabbing;
  }
  &.linking {
    cursor: crosshair;
  }
}
.canvas-sizer {
  position: relative;
}
.canvas-stage {
  position: absolute;
  inset: 0 auto auto 0;
  transform-origin: 0 0;
}
.canvas-node {
  position: absolute;
  cursor: pointer;
  touch-action: none;
  border-radius: 8px;
  &.drop-target {
    outline: 2px solid var(--resource-color);
    outline-offset: 3px;
  }
  &:active {
    cursor: grabbing;
  }
}
.node-port {
  position: absolute;
  top: var(--node-port-y);
  width: 11px;
  height: 11px;
  padding: 0;
  border: 2px solid var(--resource-color);
  background: var(--bg-content-color);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  cursor: crosshair;
  &.left-port {
    left: 0;
  }
  &.right-port {
    left: 100%;
  }
  &:hover {
    background: var(--resource-color);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--resource-color) 18%, transparent);
  }
}
.canvas-edges {
  position: absolute;
  inset: 0;
  pointer-events: none;
  .edge-line,
  .link-preview {
    fill: none;
    stroke: var(--color-primary-second);
    stroke-width: 1.8;
    opacity: 0.65;
  }
  .edge-line.pool-source {
    stroke: var(--color-purple);
  }
  .edge-line.content,
  .edge-line.frozen {
    stroke: var(--font-info-color);
    stroke-dasharray: 6 4;
  }
  .edge-line.pending:not(.frozen) {
    stroke: var(--color-warning);
    stroke-dasharray: 5 3;
  }
  .edge-line.failed:not(.frozen) {
    stroke: var(--color-error);
  }
  .edge-line.selected,
  .edge-line.related {
    stroke-width: 3;
    opacity: 1;
  }
  .edge-hit {
    fill: none;
    stroke: transparent;
    stroke-width: 14;
    cursor: pointer;
    pointer-events: stroke;
  }
  .link-preview {
    opacity: 1;
    stroke-dasharray: 5 3;
  }
}
.canvas-empty {
  position: absolute;
  inset: 50% 20px auto;
  transform: translateY(-50%);
  text-align: center;
  cursor: default;
}
.connection-form {
  width: 300px;
  max-width: calc(100vw - 48px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  p {
    margin: 0;
    color: var(--font-info-color);
    font-size: 12px;
    line-height: 1.6;
  }
}
.connection-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  > span {
    font-size: 12px;
    color: var(--font-text-color);
  }
  .intel-select {
    width: 100%;
  }
}
@media (max-width: 1100px) {
  .inventory-wrap {
    width: 200px;
  }
}
@media (max-width: 750px) {
  .board-container {
    flex-direction: column;
  }
  .inventory-wrap {
    width: auto;
    flex-basis: 180px;
    min-height: 0;
    padding: 10px 12px;
    border-right: 0;
    border-bottom: 1px solid var(--border-main-color);
    .inventory-heading,
    .inventory-hint,
    .create-shortcuts {
      display: none;
    }
    .inventory-list {
      margin-top: 6px;
    }
  }
  .board-toolbar {
    padding: 8px 10px;
  }
  .resource-legend {
    gap: 8px;
    font-size: 10px;
  }
  .zoom-label {
    min-width: 30px;
  }
}
</style>
