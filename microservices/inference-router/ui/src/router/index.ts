

import { createRouter, createWebHistory } from "vue-router";
import { routeList, notFoundAndNoPower } from "./routes";

const router = createRouter({
  history: createWebHistory(),
  routes: [...notFoundAndNoPower, ...routeList],
});

export default router;
