FROM node:22-slim
WORKDIR /app
LABEL org.triad-bluff.protocol="1.0" org.triad-bluff.runtime="2" org.triad-bluff.cpu="1" org.triad-bluff.ram-bytes="1073741824" org.triad-bluff.scratch-bytes="1073741824" org.triad-bluff.gpu="false" org.triad-bluff.gpu-bytes="0"
COPY package.json package-lock.json tsconfig.json ./
COPY src ./src
RUN npm ci && npm run build && npm prune --omit=dev
ENV HOME=/tmp
USER 10000:10000
ENTRYPOINT ["node", "dist/agent.js"]
