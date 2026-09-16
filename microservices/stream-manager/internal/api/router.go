// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Package api exposes the HTTP surface and wires routes to handlers.
package api

import (
	"github.com/gin-gonic/gin"
)

func NewRouter() *gin.Engine {
	router := gin.New()
	return router
}

// Above code is still meant as a scaffolding and should be reaplaced with actual routes
//  and handlers as needed. Unused imports are removed by go and in order to keep
// 	the gin module dependency and the mod file tidy, this code was added.
