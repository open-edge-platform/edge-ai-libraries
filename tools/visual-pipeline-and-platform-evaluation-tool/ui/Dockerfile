# Use Node.js base image for building the React app
FROM node:18 AS build

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY ui/package*.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the application code
COPY ui/ .

# Build the React app for production
RUN npm run build

# Use Nginx for serving the built app
FROM nginx:alpine

# Upgrade packages to fix possible vulnerabilities
USER root
RUN apk update && apk upgrade --no-cache && \
    rm -f /bin/dmesg \
          /usr/bin/nc \
          /bin/ping \
          /bin/base64 \
          /sbin/apk \
          /usr/bin/wget \
          /usr/bin/curl

# Create nginx user and required directories with proper permissions
RUN adduser -D -s /bin/sh nginx || true && \
    mkdir -p /var/cache/nginx/client_temp \
             /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp \
             /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    chown -R nginx:nginx /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid

# Copy the build output to Nginx's html directory (Vite builds to dist/, not build/)
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf

# Ensure nginx user owns the html directory
RUN chown -R nginx:nginx /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Set working user
USER nginx

# Start Nginx server
CMD ["nginx", "-g", "daemon off;"]
