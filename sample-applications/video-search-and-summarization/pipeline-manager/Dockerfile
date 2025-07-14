# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM node:22-alpine

WORKDIR /usr/src/app

RUN apk add --no-cache curl

COPY package*.json ./

RUN npm ci

COPY . .

RUN npm run build

EXPOSE 3000

CMD ["node", "dist/main"]