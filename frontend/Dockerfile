# Stage 1: Build TanStack Start SSR
FROM node:20-alpine AS builder
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
ENV NITRO_PRESET=node-server
RUN pnpm run build

# Stage 2: Serve dengan Node.js + Nginx
FROM node:20-alpine AS runner
RUN apk add --no-cache nginx

WORKDIR /app

# Salin output build Nitro
COPY --from=builder /app/.output ./.output

# Salin konfigurasi Nginx ke Alpine default http.d
COPY nginx.conf /etc/nginx/http.d/default.conf

# Salin startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 80

CMD ["/app/start.sh"]
