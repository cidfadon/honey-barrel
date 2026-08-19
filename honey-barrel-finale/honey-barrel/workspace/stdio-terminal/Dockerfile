FROM docker:27-cli AS docker-cli

FROM node:20-alpine

WORKDIR /app

# Docker CLI for host-engine access via mounted socket
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN ln -sf /usr/local/bin/docker /usr/bin/docker

# bash + common utilities so shell commands work as expected
RUN apk add --no-cache bash coreutils grep curl docker

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

# runtime env safety
ENV NODE_ENV=production
ENV MCP_WORKSPACE=/workspace

EXPOSE 3002

CMD ["node", "server.js"]
