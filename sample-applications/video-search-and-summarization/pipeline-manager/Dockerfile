# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Build stage
FROM node:25-alpine AS builder

RUN apk update && apk upgrade --no-cache

WORKDIR /usr/src/app

COPY package*.json ./

RUN npm ci

COPY . .

RUN npm run build

# Production stage
FROM node:25-alpine

RUN apk update && apk upgrade --no-cache

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /usr/src/app

RUN chown appuser:appgroup /usr/src/app

RUN apk add --no-cache curl

COPY package*.json ./

RUN npm ci --omit=dev --omit=optional && npm cache clean --force && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

COPY --from=builder /usr/src/app/dist ./dist

USER appuser

EXPOSE 3000

CMD ["node", "dist/main"]