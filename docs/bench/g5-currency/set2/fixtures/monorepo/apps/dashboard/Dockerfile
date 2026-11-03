FROM node:20.11.1 AS build
WORKDIR /app
COPY . .
RUN corepack enable && pnpm install --frozen-lockfile && pnpm build

FROM nginx:1.31.8
COPY --from=build /app/dist /usr/share/nginx/html
