FROM node:22

RUN apt-get update && \
    apt-get install -y nginx bash curl jq python3 g++ make git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package.json files
COPY package.json package-lock.json* ./
COPY chat-ui/ui/package.json ./chat-ui/ui/

# First, install the gateway (openclaw) globally and patch the default Control UI behavior
RUN npm install -g openclaw@latest && \
    sed -i 's/typeof crypto<"u"&&!!crypto.subtle/false/g' /usr/local/lib/node_modules/openclaw/dist/control-ui/assets/index-*.js

# Copy source code and build frontend
COPY . .
RUN mkdir -p chat-ui/ui/public/settings
RUN cd chat-ui/ui && \
    npm install && \
    npm run build

# Copy custom nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Setup start script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# The main port for Ali ECI
EXPOSE 80

CMD ["/app/entrypoint.sh"]
