// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import Layout from "@/layout/Main.vue";

export const routeList = [
  {
    path: "/",
    component: Layout,
    children: [
      {
        path: "",
        component: () => import("@/layout/Router.vue"),
        redirect: "/overview",
        children: [
          {
            path: "overview",
            name: "Overview",
            component: () => import("@/views/overview/index.vue"),
            meta: { title: "Overview" },
          },
          {
            path: "tokens",
            name: "TokenOverview",
            component: () => import("@/views/tokenOverview/index.vue"),
            meta: { title: "Tokens" },
          },
          {
            path: "latency",
            name: "LatencyOverview",
            component: () => import("@/views/latencyOverview/index.vue"),
            meta: { title: "Latency" },
          },
          {
            path: "traffic",
            name: "RouterTraffic",
            component: () => import("@/views/trafficOverview/index.vue"),
            meta: { title: "Traffic" },
          },
          {
            path: "providers",
            name: "ProviderConfig",
            component: () => import("@/views/providerConfig/index.vue"),
            meta: { title: "Providers" },
          },
          {
            path: "plugins",
            name: "PluginsConfig",
            component: () => import("@/views/pluginsConfig/index.vue"),
            meta: { title: "Plugins" },
          },
          {
            path: "policies",
            name: "PolicyConfig",
            component: () => import("@/views/policyConfig/index.vue"),
            meta: { title: "Policies" },
          },
          {
            path: "strategies",
            name: "StrategyConfig",
            component: () => import("@/views/strategyConfig/index.vue"),
            meta: { title: "Strategies" },
          },
          {
            path: "prompts",
            name: "PromptConfig",
            component: () => import("@/views/promptConfig/index.vue"),
            meta: { title: "Prompts" },
          },
        ],
      },
    ],
  },
];

export const notFoundAndNoPower = [
  {
    path: "/:path(.*)*",
    name: "notFound",
    component: () => import("@/views/error/404.vue"),
    meta: {
      title: "404",
    },
  },
];
