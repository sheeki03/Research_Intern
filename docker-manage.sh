#!/bin/bash

# Docker management script for Research Intern application

case "$1" in
    start)
        echo "🚀 Starting Research Intern..."
        docker-compose up -d
        echo "✅ Services started!"
        echo "🌐 Access the application at: http://localhost:8501"
        ;;
    stop)
        echo "🛑 Stopping Research Intern..."
        docker-compose down
        echo "✅ Services stopped!"
        ;;
    restart)
        echo "🔄 Restarting Research Intern..."
        docker-compose restart
        echo "✅ Services restarted!"
        ;;
    logs)
        echo "📋 Showing application logs..."
        docker-compose logs -f app
        ;;
    status)
        echo "📊 Service status:"
        docker-compose ps
        ;;
    shell)
        echo "🐚 Opening shell in app container..."
        docker-compose exec app bash
        ;;
    build)
        echo "🔨 Rebuilding Docker image..."
        docker-compose build --no-cache
        echo "✅ Build complete!"
        ;;
    clean)
        echo "🧹 Cleaning up Docker resources..."
        docker-compose down -v
        docker system prune -f
        echo "✅ Cleanup complete!"
        ;;
    test)
        echo "🧪 Running sitemap test..."
        docker-compose exec app python -c "
import asyncio
import sys
sys.path.append('.')
from src.core.scanner_utils import discover_sitemap_urls

async def test():
    urls = await discover_sitemap_urls('https://docs.loopfi.xyz/')
    print(f'✅ Found {len(urls)} URLs - Sitemap test PASSED' if len(urls) > 0 else '❌ Sitemap test FAILED')

asyncio.run(test())
"
        ;;
    *)
        echo "🐳 Research Intern Docker Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|logs|status|shell|build|clean|test}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the application services"
        echo "  stop    - Stop the application services"
        echo "  restart - Restart the application services"
        echo "  logs    - Show application logs (follow mode)"
        echo "  status  - Show service status"
        echo "  shell   - Open bash shell in app container"
        echo "  build   - Rebuild Docker image"
        echo "  clean   - Stop services and clean up Docker resources"
        echo "  test    - Run sitemap functionality test"
        echo ""
        echo "🌐 Application URL: http://localhost:8501"
        ;;
esac 