#!/bin/sh
set -e

# Jalankan server SSR TanStack Start di background
PORT=18080 HOST=127.0.0.1 node .output/server/index.mjs &

# Jalankan Nginx di foreground
exec nginx -g "daemon off;"
