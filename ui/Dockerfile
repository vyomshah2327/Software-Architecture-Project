# Build from the repository root:  docker build -f ui/Dockerfile -t ui .
FROM node:22-slim
WORKDIR /app
COPY ui/package*.json ./
RUN npm ci --omit=dev
COPY ui/src ./src
COPY ui/public ./public
ENV PORT=8080
EXPOSE 8080
CMD ["node", "src/server.js"]
