# Docker Setup for Memoir

This directory contains all Docker-related files for running Memoir in containers.

## Quick Start

From the project root:

```bash
# Start services using wrapper script
./docker.sh start

# Or from this directory
cd docker
./start-docker.sh start
```

Then open your browser to http://localhost:8080

**Getting Started**: Since the sample data initialization is temporarily disabled due to containerization constraints, use these commands in the UI:
- `/demo` - Explore with demo data
- `/repo` - View repository information
- `/code` - See Python integration examples

## Files in this Directory

- **Dockerfile** - Multi-stage Docker image build configuration
- **docker-compose.yml** - Production service orchestration
- **docker-compose.dev.yml** - Development overrides for live coding
- **start-docker.sh** - Convenient script with multiple commands
- **README.md** - This documentation file

## Usage Commands

All commands work from either the project root (using `./docker.sh`) or from this directory (using `./start-docker.sh`):

```bash
# Start services
./start-docker.sh start           # Production mode
./start-docker.sh start dev       # Development mode

# Manage services
./start-docker.sh stop            # Stop all services
./start-docker.sh restart         # Restart services
./start-docker.sh status          # Check service status

# Monitoring
./start-docker.sh logs            # View service logs

# Cleanup
./start-docker.sh clean           # Remove containers and data
./start-docker.sh help            # Show all commands
```

## Architecture

The Docker setup includes:

### memoir-ui Service
- **Port**: 8080:8080
- **Purpose**: Main Memoir web interface
- **Features**: Health checks, persistent data, auto-restart
- **Data**: Stored in `docker-data/` directory

### memoir-init Service (Optional)
- **Purpose**: Initialize sample data for testing
- **Runs**: Once on startup to create demo memory store
- **Note**: May show errors but doesn't affect main functionality

### Volumes
- **memoir_data**: Persistent storage for memory stores
- **Bind Mount**: `docker-data/` for easy file access

## Development Mode

Enable live code reloading:

```bash
./start-docker.sh start dev
```

This mounts your local source code into the container so changes are reflected immediately.

## File Structure

```
docker/
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Production services
├── docker-compose.dev.yml  # Development overrides
├── start-docker.sh         # Management script
└── README.md               # This file

../docker-data/             # Persistent data (created on first run)
../docker.sh                # Convenience wrapper script
```

## Troubleshooting

### Port 8080 in use
```bash
# Use different port
docker run -p 8081:8080 memoir:latest
```

### Permission issues
```bash
# Fix data directory permissions
sudo chown -R $USER:$USER docker-data/
```

### Build issues
```bash
# Clean rebuild
./start-docker.sh clean
./start-docker.sh start
```

### Service not responding
```bash
# Check logs
./start-docker.sh logs

# Check container status
docker ps
```

For more detailed troubleshooting, see the main [DOCKER.md](DOCKER.md) file.

## Integration with Project

The Docker configuration is designed to work seamlessly with the main Memoir project:

- **Build Context**: Uses parent directory so all source code is available
- **Dependencies**: Automatically installs all project requirements
- **Development**: Supports live code mounting for active development
- **Production**: Optimized for deployment with health checks and restarts

This structure keeps Docker files organized while maintaining full integration with the Memoir codebase.
