FROM node:22-bookworm-slim

WORKDIR /app

COPY web/package*.json ./
RUN npm install

COPY web ./

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
