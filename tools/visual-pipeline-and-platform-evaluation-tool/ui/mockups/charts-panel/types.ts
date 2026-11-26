// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { FakePoint } from "./fakeMetrics";

export type PanelProps = {
  history: FakePoint[];
  elapsed: number;
  running: boolean;
  gpu: number;
  setGpu: (gpu: number) => void;
};
