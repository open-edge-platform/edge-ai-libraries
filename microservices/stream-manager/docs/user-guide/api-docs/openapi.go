// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package apidocs embeds the published OpenAPI spec for Stream Manager.
package apidocs

import _ "embed"

//go:embed openapi.yaml
var OpenapiSpec string
