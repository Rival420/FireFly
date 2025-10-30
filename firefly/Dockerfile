FROM node:18-alpine
WORKDIR /app
COPY package.json package-lock.json ./
ARG USE_NPM_CI=true
RUN if [ "$USE_NPM_CI" = "true" ]; then npm ci; else npm install; fi
COPY . .
ENV PORT=3000 HOST=0.0.0.0
EXPOSE 3000
CMD ["npm", "start"]