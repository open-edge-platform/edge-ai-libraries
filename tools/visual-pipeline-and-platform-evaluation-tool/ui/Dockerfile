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

# Set non-root user
USER nginx

# Copy the build output to Nginx's html directory (Vite builds to dist/, not build/)
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Start Nginx server
CMD ["nginx", "-g", "daemon off;"]
