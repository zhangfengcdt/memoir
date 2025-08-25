#!/bin/bash

# Memoir Docker Wrapper Script
# This script provides easy access to Docker commands from the project root

set -e

# Change to docker directory and run the actual script
cd docker
./start-docker.sh "$@"