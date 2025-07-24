# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM node:20-slim AS vite-app

WORKDIR /user/app

COPY package*.json /user/app/

RUN ["npm", "ci"]

COPY . .

RUN ["npm", "run", "build"]

FROM nginx:1.27.4

COPY --from=vite-app /user/app/dist /user/share/nginx/html
COPY ./env.sh /docker-entrypoint.d/env.sh

COPY ./nginx.conf /etc/nginx/conf.d/default.conf
RUN chmod +x /docker-entrypoint.d/env.sh
EXPOSE 80