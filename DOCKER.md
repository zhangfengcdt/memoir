# Docker Setup for Memoir

This guide explains how to run Memoir using Docker for easy setup and testing.

## Quick Start

### Option 1: Using Startup Script (Easiest)

```bash
# Clone the repository
git clone https://github.com/yourusername/memoir.git
cd memoir

# Start with the convenient script
./start-docker.sh start

# Or for development mode
./start-docker.sh start dev

# Open your browser (script will show the URL)
```

### Option 2: Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/memoir.git
cd memoir

# Start the services
docker-compose up -d

# Open your browser
open http://localhost:8080
```

### Option 2: Using Docker directly

```bash
# Build the image
docker build -t memoir:latest .

# Run the container
docker run -d \
  --name memoir-ui \
  -p 8080:8080 \
  -v memoir_data:/app/data/memory_stores \
  memoir:latest

# Open your browser
open http://localhost:8080
```

## Detailed Usage

### Building the Image

```bash
# Build with default settings
docker build -t memoir:latest .

# Build with specific tag
docker build -t memoir:v1.0.0 .

# Build with build arguments (if needed)
docker build --build-arg PYTHON_VERSION=3.11 -t memoir:latest .
```

### Running the Container

#### Basic Run
```bash
docker run -p 8080:8080 memoir:latest
```

#### With Persistent Storage
```bash
# Create a volume for data persistence
docker volume create memoir_data

# Run with volume mounted
docker run -d \
  --name memoir-ui \
  -p 8080:8080 \
  -v memoir_data:/app/data/memory_stores \
  memoir:latest
```

#### With Local Directory Mount (Development)
```bash
# Mount local directory for development
docker run -d \
  --name memoir-ui \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data/memory_stores \
  memoir:latest
```

### Docker Compose Services

The `docker-compose.yml` includes two services:

#### memoir-ui (Main Service)
- **Port**: 8080:8080
- **Function**: Runs the Memoir UI server
- **Volumes**: Persistent data storage
- **Health Check**: HTTP health check on port 8080

#### memoir-init (Optional Initialization)
- **Function**: Initializes sample memory store data
- **Runs Once**: Creates demo data for testing
- **Dependency**: Starts after memoir-ui

### Environment Variables

You can customize the container using environment variables:

```bash
docker run -d \
  --name memoir-ui \
  -p 8080:8080 \
  -e MEMOIR_DATA_DIR=/app/data/memory_stores \
  -e PYTHONPATH=/app \
  memoir:latest
```

Available environment variables:
- `MEMOIR_DATA_DIR`: Directory for memory stores (default: `/app/data/memory_stores`)
- `PYTHONPATH`: Python path (default: `/app`)

### Data Persistence

#### Using Docker Volumes (Recommended)
```bash
# Create named volume
docker volume create memoir_data

# Use in container
docker run -v memoir_data:/app/data/memory_stores memoir:latest
```

#### Using Bind Mounts
```bash
# Create local directory
mkdir -p ./docker-data

# Mount local directory
docker run -v $(pwd)/docker-data:/app/data/memory_stores memoir:latest
```

## Development with Docker

### Development Mode
```bash
# Use docker-compose with development overrides
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Or mount your local code for live development
docker run -d \
  --name memoir-dev \
  -p 8080:8080 \
  -v $(pwd):/app \
  -v memoir_data:/app/data/memory_stores \
  memoir:latest
```

### Accessing the Container
```bash
# Execute commands in running container
docker exec -it memoir-ui bash

# View logs
docker logs memoir-ui

# Follow logs
docker logs -f memoir-ui
```

## Startup Script Commands

The included `start-docker.sh` script provides convenient commands:

```bash
# Start the service
./start-docker.sh start

# Start in development mode
./start-docker.sh start dev

# Stop the service
./start-docker.sh stop

# Restart the service
./start-docker.sh restart

# View logs
./start-docker.sh logs

# Check status
./start-docker.sh status

# Clean up everything
./start-docker.sh clean

# Show help
./start-docker.sh help
```

## Testing the Setup

1. **Start the service**:
   ```bash
   ./start-docker.sh start
   # OR
   docker-compose up -d
   ```

2. **Open your browser**: http://localhost:8080

3. **Test the UI**:
   ```bash
   # Connect to sample store
   /connect /app/data/memory_stores/sample_store
   
   # Generate a proof
   /proof profile.personal.name
   
   # Verify the proof
   /verify
   ```

## Troubleshooting

### Common Issues

#### Port Already in Use
```bash
# Check what's using port 8080
lsof -i :8080

# Use different port
docker run -p 8081:8080 memoir:latest
```

#### Permission Issues
```bash
# Fix volume permissions
docker run --rm -v memoir_data:/data alpine chown -R 1000:1000 /data
```

#### Build Failures
```bash
# Clean build (no cache)
docker build --no-cache -t memoir:latest .

# Check logs during build
docker build -t memoir:latest . 2>&1 | tee build.log
```

### Health Checks

Check if the service is healthy:
```bash
# Check container health
docker inspect memoir-ui | grep Health -A 10

# Manual health check
curl http://localhost:8080/ || echo "Service not responding"
```

## Cleanup

### Remove Containers
```bash
# Stop and remove containers
docker-compose down

# Or manually
docker stop memoir-ui memoir-init
docker rm memoir-ui memoir-init
```

### Remove Data (Careful!)
```bash
# Remove volumes (this deletes all data)
docker volume rm memoir_data

# Remove images
docker rmi memoir:latest
```

### Complete Cleanup
```bash
# Remove everything related to memoir
docker-compose down -v --rmi all
docker system prune -f
```

## Production Deployment

### Using Docker Compose in Production
```bash
# Use production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# With specific resource limits
docker-compose up -d --scale memoir-ui=2
```

### Security Considerations
- The container runs as non-root user (`appuser`)
- Minimal base image (python:3.11-slim)
- Only necessary ports exposed
- Health checks enabled
- Read-only root filesystem (add `--read-only` flag if needed)

### Monitoring
```bash
# Monitor resource usage
docker stats memoir-ui

# Check health
docker inspect memoir-ui --format='{{.State.Health.Status}}'
```

## Advanced Usage

### Custom Dockerfile
Create your own Dockerfile extending the base:
```dockerfile
FROM memoir:latest

# Add custom configurations
COPY custom-config.json /app/config/

# Override startup command
CMD ["python", "-m", "src.memoir.ui.serve_ui", "--config", "/app/config/custom-config.json"]
```

### Multi-stage Builds
For smaller production images, consider multi-stage builds to separate build dependencies from runtime.

### Integration with CI/CD
```yaml
# Example GitHub Actions workflow
- name: Build Docker image
  run: docker build -t memoir:${{ github.sha }} .

- name: Test image
  run: |
    docker run -d --name test-memoir -p 8080:8080 memoir:${{ github.sha }}
    sleep 10
    curl -f http://localhost:8080 || exit 1
    docker stop test-memoir
```