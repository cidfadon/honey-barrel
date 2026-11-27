FROM node:22-alpine

WORKDIR /data

RUN apk add --no-cache python3 make g++ git \
 && npm install -g openclaw@latest

ENV OPENCLAW_PORT=8080
EXPOSE 8080

CMD ["openclaw", "start", "--host", "0.0.0.0", "--port", "8080"]
