#!/bin/bash

# Memoir Docker Startup Script
# This script provides an easy way to start Memoir with Docker

set -e

echo "🔬 Memoir - Git for AI Memory"
echo "=============================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not available. Please install Docker Compose."
    exit 1
fi

# Create data directory  
echo "📁 Setting up Docker volumes..."

# Function to use docker-compose or docker compose
run_compose() {
    if command -v docker-compose &> /dev/null; then
        docker-compose "$@"
    else
        docker compose "$@"
    fi
}

# Parse command line arguments
COMMAND=${1:-"start"}
MODE=${2:-"prod"}

case $COMMAND in
    "start")
        echo "🚀 Starting Memoir UI service..."
        if [ "$MODE" = "dev" ]; then
            echo "   Mode: Development"
            run_compose -f docker-compose.yml -f docker-compose.dev.yml up -d
        else
            echo "   Mode: Production"
            run_compose up -d
        fi
        
        echo ""
        echo "⏳ Waiting for service to be ready..."
        sleep 5
        
        # Wait for service to be healthy
        for i in {1..30}; do
            if curl -s http://localhost:8080 > /dev/null 2>&1; then
                echo "✅ Memoir UI is ready!"
                echo ""
                echo "🌐 Open your browser to:"
                echo "   http://localhost:8080"
                echo ""
                echo "🧪 Try these commands in the UI:"
                echo "   /demo                           # Show demo data for exploration"
                echo "   /repo                           # Show repository information"  
                echo "   /code                           # Show Python integration code"
                echo "   /proof profile.personal.name    # Generate cryptographic proof"
                echo "   /verify                         # Verify the generated proof"
                echo ""
                echo "📚 For more help:"
                echo "   • Type /help in the UI"
                echo "   • Read DOCKER.md for detailed instructions"
                echo "   • Check docker logs: docker logs memoir-ui-service"
                exit 0
            fi
            echo -n "."
            sleep 2
        done
        
        echo ""
        echo "⚠️  Service might be starting slowly. Check status with:"
        echo "   docker logs memoir-ui-service"
        ;;
        
    "stop")
        echo "🛑 Stopping Memoir services..."
        run_compose down
        echo "✅ Services stopped."
        ;;
        
    "restart")
        echo "🔄 Restarting Memoir services..."
        run_compose down
        run_compose up -d
        echo "✅ Services restarted."
        ;;
        
    "logs")
        echo "📋 Showing Memoir service logs..."
        run_compose logs -f memoir-ui
        ;;
        
    "status")
        echo "📊 Memoir service status:"
        run_compose ps
        echo ""
        if curl -s http://localhost:8080 > /dev/null 2>&1; then
            echo "🟢 Service is responding at http://localhost:8080"
        else
            echo "🔴 Service is not responding"
        fi
        ;;
        
    "clean")
        echo "🧹 Cleaning up Memoir services and data..."
        echo "⚠️  This will remove all containers, volumes, and data!"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            run_compose down -v --rmi local
            docker volume rm memoir_data 2>/dev/null || true
            # Docker volumes will be removed by docker-compose down -v
            echo "✅ Cleanup complete."
        else
            echo "❌ Cleanup cancelled."
        fi
        ;;
        
    "help")
        echo "📖 Memoir Docker Commands:"
        echo ""
        echo "  start [prod|dev]  - Start the service (default: prod)"
        echo "  stop              - Stop the service"
        echo "  restart           - Restart the service"
        echo "  logs              - Show service logs"
        echo "  status            - Check service status"
        echo "  clean             - Remove all containers and data"
        echo "  help              - Show this help"
        echo ""
        echo "Examples:"
        echo "  ./start-docker.sh start         # Start in production mode"
        echo "  ./start-docker.sh start dev     # Start in development mode"
        echo "  ./start-docker.sh logs          # View logs"
        echo "  ./start-docker.sh clean         # Clean everything"
        ;;
        
    *)
        echo "❌ Unknown command: $COMMAND"
        echo "   Use './start-docker.sh help' for available commands"
        exit 1
        ;;
esac