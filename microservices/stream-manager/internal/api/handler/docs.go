// SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

package handler

import (
	"github.com/gin-gonic/gin"
	swaggerfiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
	"github.com/swaggo/swag"

	apidoc "github.com/open-edge-platform/edge-ai-libraries/microservices/stream-manager/docs/user-guide/api-docs"
)

// embeddedSpec implements swag.Swagger so the embedded OpenAPI YAML can be
// handed to gin-swagger without the need to explicitly expose the file over HTTP.
type embeddedSpec string

func (s embeddedSpec) ReadDoc() string { return string(s) }

func init() {
	swag.Register("v1", embeddedSpec(apidoc.OpenapiSpec))
}

func ServeSwaggerUI(c *gin.Context) {
	swaggerHandler := ginSwagger.WrapHandler(swaggerfiles.Handler, ginSwagger.InstanceName("v1"))
	swaggerHandler(c)
}
