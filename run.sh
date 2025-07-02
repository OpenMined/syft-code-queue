#!/bin/bash
set -e

# SyftBox app entry point for syft-code-queue
# This script starts the job browser UI service

echo "🚀 Syft Code Queue UI - Starting job browser service..."

# Disable interactive prompts and shell customizations for non-interactive environments
export ZSH_DISABLE_COMPFIX=true
export NONINTERACTIVE=1

# Create virtual environment with uv (remove old one if exists)
echo "📦 Setting up virtual environment with uv..."
rm -rf .venv

# Let uv handle Python version management - it will download if needed
echo "🐍 Creating virtual environment with Python 3.12..."
uv venv --python 3.12

# Set the virtual environment path for uv to use
export VIRTUAL_ENV="$(pwd)/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies using uv sync (which respects the virtual environment)
echo "📦 Installing dependencies..."
uv sync

# Build the frontend
echo "🔨 Building frontend..."
cd frontend
if command -v bun &> /dev/null; then
    echo "Using bun to build frontend..."
    bun install
    bun run build
elif command -v npm &> /dev/null; then
    echo "Using npm to build frontend..."
    npm install
    npm run build
else
    echo "⚠️  Neither bun nor npm found. Frontend will not be built."
fi
cd ..

# Start the backend API server
echo "🌐 Starting job browser UI backend on port ${SYFTBOX_ASSIGNED_PORT:-8002}..."
SYFTBOX_ASSIGNED_PORT=${SYFTBOX_ASSIGNED_PORT:-8002}
uv run uvicorn backend.main:app --host 0.0.0.0 --port $SYFTBOX_ASSIGNED_PORT 