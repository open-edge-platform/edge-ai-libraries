// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Link, useLocation } from "react-router";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";

export const NotFound = () => {
  const { pathname } = useLocation();

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <h1 className="text-3xl font-bold">Page not found</h1>
      <p className="text-muted-foreground mt-2">
        There is no page at <span className="font-mono">{pathname}</span>.
      </p>
      <Link
        to="/"
        className="mt-6 inline-block text-sm text-primary hover:underline"
      >
        Go to Dashboard
      </Link>
    </div>
  );
};
