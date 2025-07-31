# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM node:20-slim AS vite-app

WORKDIR /user/app

COPY package*.json /user/app/

RUN ["npm", "ci"]

COPY . .

RUN ["npm", "run", "build"]

FROM nginxinc/nginx-unprivileged:1.28.0
USER root
ARG DOCROOT=/user/share/nginx/html

COPY --from=vite-app --chown=nginx:nginx /user/app/dist ${DOCROOT}
COPY --chown=nginx:nginx ./env.sh /docker-entrypoint.d/env.sh
COPY --chown=nginx:nginx ./nginx.conf /etc/nginx/conf.d/default.conf

RUN find ${DOCROOT} -type d -print0 | xargs -0 chmod 755 && \
    find ${DOCROOT} -type f -print0 | xargs -0 chmod 644 && \
    chmod 755 ${DOCROOT} && \
    chmod +x /docker-entrypoint.d/env.sh

USER nginx
EXPOSE 8080