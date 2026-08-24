# syntax=docker/dockerfile:1.6
# ---- Build stage ----------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .

# Empty by default: the runtime stage serves this build behind nginx, which
# proxies /api/ to the backend. Every fetch in src/ already spells out the
# full /api/v1/... path, so a non-empty prefix here yields /api/api/v1/...
# and 404s. Dev (vite) falls back to http://localhost:5001 in AppContext.
ARG VITE_API_URL=
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_STRIPE_PUBLISHABLE_KEY
ENV VITE_API_URL=$VITE_API_URL \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_STRIPE_PUBLISHABLE_KEY=$VITE_STRIPE_PUBLISHABLE_KEY

RUN npm run build

# ---- Runtime stage --------------------------------------------------------
FROM nginx:1.31-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
