# Dhanz GPT: one image, any sign-in mode (AUTH_MODE is read at run time).
FROM node:22-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN NEXT_STANDALONE=1 npm run build

FROM node:22-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
# The server bundle, its static files, and what the database script needs (migrations and the postgres client).
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
COPY --from=build /app/db ./db
COPY --from=build /app/scripts/db.mjs ./scripts/db.mjs
COPY --from=build /app/node_modules/postgres ./node_modules/postgres
# Uploaded files and the local email outbox live here; mount a volume on it.
RUN mkdir -p /app/.data && chown -R node:node /app/.data
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
