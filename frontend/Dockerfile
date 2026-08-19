# Built from the repository root so the shared Nginx config is in context.
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin deployment: the SPA calls /api on its own host, so no absolute
# backend URL and no production CORS exception are needed.
ENV VITE_API_URL=""
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx/app.conf /etc/nginx/conf.d/default.conf
