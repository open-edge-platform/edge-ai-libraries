<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->
<template>
  <section class="request-traffic" :aria-label="t('router.traffic.requests')">
    <div class="traffic-totals">
      <div class="total-item">
        <span
          ><LoginOutlined /> {{ t("router.traffic.incoming") }} Request</span
        >
        <strong>{{ format(totals.incoming) }}</strong>
      </div>
      <div class="total-item">
        <span
          ><LogoutOutlined /> {{ t("router.traffic.outgoing") }} Request</span
        >
        <strong>{{ format(totals.outgoing) }}</strong>
      </div>
      <div class="total-item">
        <span>{{ t("router.traffic.source") }}</span>
        <strong>{{ format(sourceCount) }}</strong>
      </div>
      <div class="total-item">
        <span>{{ t("router.traffic.provider") }}</span>
        <strong>{{ format(providerCount) }}</strong>
      </div>
    </div>

    <TrafficGraph
      v-if="snapshot.nodes.length"
      :snapshot="snapshot"
      mode="requests"
    />
    <div v-else class="empty-state">
      <a-empty :description="t('router.traffic.empty')" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { LoginOutlined, LogoutOutlined } from "@ant-design/icons-vue";
import { boundaryFlow } from "../type";
import type { TrafficSnapshot } from "../type";
import TrafficGraph from "../TrafficGraph.vue";

const props = defineProps<{ snapshot: TrafficSnapshot }>();
const { t, locale } = useI18n();
const format = (value: number) =>
  new Intl.NumberFormat(locale.value.replace("_", "-")).format(value);
const totals = computed(() => boundaryFlow(props.snapshot, "requests"));
const sourceCount = computed(
  () => props.snapshot.nodes.filter((node) => node.kind === "source").length,
);
const providerCount = computed(
  () => props.snapshot.nodes.filter((node) => node.kind === "provider").length,
);
</script>

<style scoped lang="less">
.request-traffic {
  min-width: 0;
}
.traffic-totals {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 8px 0 10px;
}
.total-item {
  min-width: 0;
  padding: 0 20px;
  border-left: 1px solid var(--border-main-color);
}
.total-item:first-child {
  padding-left: 0;
  border-left: 0;
}
.total-item > span {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  color: var(--font-tip-color);
  font-size: 12px;
}
.total-item > strong {
  display: block;
  margin-top: 8px;
  font-size: 26px;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.empty-state {
  min-height: 440px;
  display: grid;
  place-items: center;
}
@media (max-width: 1100px) {
  .total-item {
    padding: 0 12px;
  }
  .total-item > strong {
    font-size: 22px;
  }
}
@media (max-width: 600px) {
  .traffic-totals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 20px 0;
  }
  .total-item:nth-child(3) {
    padding-left: 0;
    border-left: 0;
  }
}
</style>
