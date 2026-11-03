FROM node:18.19.1 AS build
WORKDIR /app
COPY . .
RUN npm ci && npm run build

FROM nginx:1.24.0
COPY --from=build /app/dist /usr/share/nginx/html
