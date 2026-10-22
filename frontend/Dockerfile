# syntax=docker/dockerfile:1

# ---- Builder stage ----
FROM node:20-alpine AS builder
WORKDIR /app

# Copy lockfile and package.json first (for layer caching)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

# Copy the rest of the source code
COPY frontend/ .

# Build the Vite production bundle
RUN npm run build

# ---- Production stage ----
FROM nginx:alpine
# Copy built files into nginx html directory
COPY --from=builder /app/dist /usr/share/nginx/html
# Expose the port that nginx serves on (default 80)
EXPOSE 80
# Use the default nginx entrypoint
CMD ["nginx", "-g", "daemon off;"]
