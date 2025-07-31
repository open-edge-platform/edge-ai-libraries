# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM node:22-alpine

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /usr/src/app

RUN chown appuser:appgroup /usr/src/app

RUN apk add --no-cache curl

COPY package*.json ./

USER appuser

RUN npm ci

COPY . .

RUN npm run build

USER appuser

EXPOSE 3000

CMD ["node", "dist/main"]