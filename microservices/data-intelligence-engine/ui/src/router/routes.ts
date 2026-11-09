// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export const routeList = [
  {
    path: "/",
    name: "Console",
    component: () => import("@/layout/main.vue"),
    redirect: "/libraries",
    children: [
      {
        path: "libraries",
        name: "ConsoleLibraries",
        component: () => import("@/views/libraries/index.vue"),
        meta: { consolePage: "libraries" },
      },
      {
        path: "assets",
        name: "ConsoleAssets",
        component: () => import("@/views/assets/index.vue"),
        meta: { consolePage: "assets" },
      },
      {
        path: "pools",
        name: "ConsolePools",
        component: () => import("@/views/pools/index.vue"),
        meta: { consolePage: "pools" },
      },
      {
        path: "sources",
        name: "ConsoleSources",
        component: () => import("@/views/sources/index.vue"),
        meta: { consolePage: "sources" },
      },
      {
        path: "databases",
        name: "ConsoleDatabases",
        component: () => import("@/views/databases/index.vue"),
        meta: { consolePage: "databases" },
      },
      {
        path: "models",
        name: "ConsoleModels",
        component: () => import("@/views/ModelManagement/index.vue"),
        meta: { consolePage: "models" },
      },
      {
        path: "canvas",
        name: "ConsoleCanvas",
        component: () => import("@/views/canvas/index.vue"),
        meta: { consolePage: "canvas" },
      },
      {
        path: "retrieve",
        name: "ConsoleRetrieve",
        component: () => import("@/views/retrieve/index.vue"),
        meta: { consolePage: "retrieve" },
      },
      {
        path: "chat",
        name: "ConsoleChat",
        component: () => import("@/views/chat/index.vue"),
        meta: { consolePage: "chat" },
      },
    ],
  },
  {
    path: "/:path(.*)*",
    name: "notFound",
    component: () => import("@/views/error/404.vue"),
  },
];
