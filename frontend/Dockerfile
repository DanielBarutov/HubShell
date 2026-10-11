FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api/v1
ARG VITE_GAMECLUB_DATA_MODE=live
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_GAMECLUB_DATA_MODE=$VITE_GAMECLUB_DATA_MODE

RUN npm run build

FROM node:22-alpine AS dev

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api/v1
ARG VITE_GAMECLUB_DATA_MODE=live
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_GAMECLUB_DATA_MODE=$VITE_GAMECLUB_DATA_MODE

EXPOSE 3101

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3100"]

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
