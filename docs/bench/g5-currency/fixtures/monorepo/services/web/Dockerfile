FROM node:18.20.4 AS build
WORKDIR /app
COPY . .
RUN npm ci

FROM nginx:1.25.5
COPY --from=build /app /usr/share/nginx/html
