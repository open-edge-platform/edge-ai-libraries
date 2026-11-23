// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { createRouter, createWebHistory } from "vue-router";
import { routeList } from "./routes";

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: routeList,
});
