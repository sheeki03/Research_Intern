#!/bin/bash

# Docker run script for Research Intern application
# This script builds and runs the application with proper environment setup

set -e

echo "🐳 Starting Research Intern Docker Setup..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating a template..."
    cat > .env << EOF
# OpenRouter API Key (required)
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Application Environment
APP_ENV=development
DEBUG=true
LOG_LEVEL=info

# Output Configuration
OUTPUT_FORMAT=markdown
MAX_REQUESTS_PER_HOUR=100

# Firecrawl Configuration
FIRECRAWL_API_URL=https://j12d832.impossible.finance
EOF
    echo "📝 Please edit .env file with your API keys before running again."
    exit 1
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs reports config output cache

# Build the Docker image
echo "🔨 Building Docker image..."
docker-compose build --no-cache

# Start the services
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check if services are running
echo "🔍 Checking service status..."
docker-compose ps

# Show logs
echo "📋 Application logs:"
docker-compose logs app --tail=20

echo ""
echo "✅ Research Intern is now running!"
echo "🌐 Access the application at: http://localhost:8501"
echo ""
echo "📊 Useful commands:"
echo "  View logs:     docker-compose logs -f app"
echo "  Stop services: docker-compose down"
echo "  Restart:       docker-compose restart"
echo "  Shell access:  docker-compose exec app bash"
echo "" 