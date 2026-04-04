FROM oven/bun:1 AS base

WORKDIR /app

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser

# ----- Development -----
FROM base AS development
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 5173
CMD ["bun", "run", "dev", "--host", "0.0.0.0"]

# ----- Build -----
FROM base AS builder
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN bun run build

# ----- Production (nginx) -----
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
