FROM node:20-alpine AS build

RUN apk add --no-cache \
    fd \
    bash \
    grep \
    findutils \
    coreutils \
    net-tools \
    curl \
    tini

WORKDIR /app

# Install ALL dependencies (including devDependencies)
COPY package*.json ./
RUN npm ci

# Copy source
COPY . .

# Build TypeScript → dist/
RUN npm run build


# ---------------- Production Image ----------------

FROM node:20-alpine

RUN apk add --no-cache bash net-tools curl tini

ENTRYPOINT ["/sbin/tini", "--"]

WORKDIR /app

# Install ONLY production dependencies
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

# Copy compiled output from build stage
COPY --from=build /app/dist ./dist

ENV NODE_ENV=production
ENV WORKSPACE_ROOT=/workspace
ENV LOG_LEVEL=debug

EXPOSE 3001

CMD ["node", "dist/index.js"]

