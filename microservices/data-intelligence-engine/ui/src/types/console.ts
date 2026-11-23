// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { Library } from "@/api/console/type";

export interface ConsolePageProps {
  libraryList: Library[];
  libraryData?: Library;
}
