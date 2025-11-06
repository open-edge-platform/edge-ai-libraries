# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Stage 1: Build Vite app
FROM node:20-slim AS vite-app

# -----------------------------------------------------------------------------
# Define build-time arguments for user and group IDs.
# Default to 101, which matches the UID/GID of the 'nginx' user in the final stage.
# This ensures file ownership compatibility across stages without needing chown.
# -----------------------------------------------------------------------------
ARG UID=101
ARG GID=101

# Create a non-root user with the specified UID and GID
RUN groupadd -g ${GID} user && \
    useradd -m -s /bin/bash -u ${UID} -g ${GID} user

# Switch to the non-root user
USER user
WORKDIR /user/app

# Copy only necessary files for dependency installation
COPY package*.json /user/app/
COPY .npmrc /user/app/

# Install dependencies using clean install
RUN ["npm", "ci"]

# Copy the rest of the application source code
COPY . .

# Build the Vite application
RUN ["npm", "run", "build"]


# -----------------------------------------------------------------------------
# Stage 2: Serve the built app using Nginx (unprivileged)
# -----------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.29.2

# Copy the built app from the previous stage
COPY --from=vite-app /user/app/dist /opt/share/nginx/html

# Copy environment script and custom Nginx configuration
COPY ./env.sh /docker-entrypoint.d/env.sh
COPY ./nginx.conf /etc/nginx/nginx.conf

# Ensure the entrypoint script is executable
USER root
RUN chmod +x /docker-entrypoint.d/env.sh

# Revert to the unprivileged nginx user (UID/GID 101)
USER nginx
