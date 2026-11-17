# Stage 1: Build React
FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
# Sesuaikan output folder jika pakai CRA (build/) atau Vite (dist/)
RUN npm run build

# Stage 2: Serve dengan Nginx
FROM nginx:alpine
# Hapus konfigurasi default nginx
RUN rm /etc/nginx/conf.d/default.conf
# Salin konfigurasi custom
COPY nginx.conf /etc/nginx/conf.d/
# Salin hasil build dari Stage 1 (ganti 'dist' ke 'build' jika memakai Create React App)
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
