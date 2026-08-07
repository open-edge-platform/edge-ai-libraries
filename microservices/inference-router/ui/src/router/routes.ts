

import Layout from "@/layout/Main.vue";

export const routeList = [
  {
    path: "/",
    name: "Main",
    component: Layout,
    redirect: "/home",
    children: [
      {
        path: "/home",
        name: "Home",
        component: () => import("@/views/home/index.vue"),
        meta: { title: "Home" },
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
