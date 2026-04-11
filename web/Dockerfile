FROM node:20-alpine AS build

ARG VITE_API_BASE_URL=https://api.ailookstudio.ru
ARG VITE_HIDE_PHONE_AUTH=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_HIDE_PHONE_AUTH=${VITE_HIDE_PHONE_AUTH}

WORKDIR /build

# Copy design system tokens (needed for CSS variables at build time)
COPY AICADS-/packages/core/config/ AICADS-/packages/core/config/

# Copy web app
COPY web/package.json web/package-lock.json* web/
WORKDIR /build/web
RUN npm ci

# Copy rest of web sources + tailwind config (references AICADS- paths)
WORKDIR /build
COPY web/ web/
COPY AICADS-/packages/core/components/ AICADS-/packages/core/components/

WORKDIR /build/web
RUN npx vite build

# --- Production ---
FROM nginx:alpine

COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/web/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
