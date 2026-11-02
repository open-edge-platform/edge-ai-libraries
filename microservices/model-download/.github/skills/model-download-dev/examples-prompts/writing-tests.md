<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Write unit tests for a `MyHubPlugin` downloader using the repository's existing pytest patterns:
- Verify plugin properties and case-insensitive hub matching
- Test a successful asynchronous download
- Verify request-provided and environment-provided authentication tokens
- Check container-to-host path rewriting
- Confirm provider errors are propagated
- Patch provider functions where the plugin imports and uses them

Run the targeted unit tests and confirm they pass.
