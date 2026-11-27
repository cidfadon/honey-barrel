FROM node:20-alpine

# system deps (MCP + tooling layer)
RUN apk add --no-cache \
    git \
    ripgrep \
    bash \
    grep \
    findutils \
    coreutils \
    sysstat \
    curl \
    tini

# use proper process init (important for MCP subprocess stability)
ENTRYPOINT ["/sbin/tini", "--"]

WORKDIR /app

# dependencies first (better cache layer)
COPY package*.json ./
RUN npm ci --omit=dev

# app source
COPY . .

# runtime env safety
ENV NODE_ENV=production
ENV MCP_WORKSPACE=/workspace

EXPOSE 3002

CMD ["node", "server.js"]
