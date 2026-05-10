FROM node:20-alpine AS build

# Variant B build defaults: global SPA targeting the Railway API.
# Overridden per-deployment in CI (RU edge build sets VITE_MARKET_ID=ru,
# VITE_API_BASE_URL='' for nginx /api proxy, and VITE_WEB_ORIGIN to the
# RU public origin).
ARG VITE_API_BASE_URL=https://app-production-6986.up.railway.app
ARG VITE_MARKET_ID=global
ARG VITE_WEB_ORIGIN=https://ailookstudio.vercel.app
ARG VITE_SUPPORT_EMAIL=support@ailookstudio.ru
ARG DEPLOY_GIT_SHA=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_MARKET_ID=${VITE_MARKET_ID}
ENV VITE_WEB_ORIGIN=${VITE_WEB_ORIGIN}
ENV VITE_SUPPORT_EMAIL=${VITE_SUPPORT_EMAIL}
ENV DEPLOY_GIT_SHA=${DEPLOY_GIT_SHA}

WORKDIR /build

COPY web/package.json web/package-lock.json* web/
WORKDIR /build/web
RUN npm ci

WORKDIR /build
COPY web/ web/

WORKDIR /build/web
RUN npx vite build

# --- Production ---
FROM nginx:alpine

COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/web/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
