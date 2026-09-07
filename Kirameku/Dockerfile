FROM docker.m.daocloud.io/node:22
WORKDIR /app

# 先装依赖（利用缓存层）
COPY package*.json pnpm-workspace.yaml ./
RUN npm install --no-audit --no-fund

# 复制源码并构建
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]