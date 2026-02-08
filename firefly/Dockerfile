# =============================================================
# Stage 1 — Build the React app (runs once during docker build)
# =============================================================
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

# =============================================================
# Stage 2 — Serve static files with nginx (starts in <1 second)
# =============================================================
FROM nginx:stable-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
