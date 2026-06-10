# Use official slim Node base image
FROM node:20-slim

# Set working directory inside container
WORKDIR /app

# Copy package files first
COPY package*.json ./

# Install packages
RUN npm install

# Copy source code (excluding those in .dockerignore)
COPY . .

# Run container as non-root user (node user is built-in with UID/GID 1000)
RUN chown -R node:node /app
USER node

# Expose Vite dev server port
EXPOSE 3000

# Start Vite server
CMD ["npm", "run", "dev"]
