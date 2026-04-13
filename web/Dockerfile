FROM node:20-alpine AS build

ARG VITE_API_BASE_URL=https://api.ailookstudio.ru
ARG DEPLOY_GIT_SHA=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
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
