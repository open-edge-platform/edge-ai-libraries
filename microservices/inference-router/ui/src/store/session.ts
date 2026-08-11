// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { defineStore } from "pinia";

interface SessionState {
  currentSession: string;
}

export const sessionAppStore = defineStore("session-app-store", {
  state: (): SessionState => ({
    currentSession: "",
  }),
  actions: {
    setSessionId(sessionId: string) {
      this.currentSession = sessionId;
    },
  },
  persist: true,
});
