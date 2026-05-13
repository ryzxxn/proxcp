FROM node:20-slim

# Install build dependencies for better-sqlite3
RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy application code
COPY . .

# Build the Next.js app
# NEXT_PUBLIC_ variables must be available at build time for Next.js to inline them
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# Expose frontend port
EXPOSE 3005

# Start the application on port 3005
CMD ["sh", "-c", "node scripts/init-db.js && npm run start -- -p 3005"]
