#!/bin/bash
set -e

echo "🚀 Syft-Code-Queue Release Script (UV-based)"
echo "============================================"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if we're on main branch
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    echo "❌ Must be on main branch to release. Current branch: $BRANCH"
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "❌ You have uncommitted changes. Please commit or stash them first."
    exit 1
fi

echo "✅ Pre-flight checks passed"

# Sync dependencies
echo "📦 Syncing dependencies with uv..."
uv sync

# Run tests
echo "🧪 Running tests..."
uv run pytest tests/ -v

# Run linting
echo "🔍 Running linting..."
uv run ruff check

# Run formatting check
echo "📝 Checking formatting..."
uv run ruff format --check

# Build package
echo "🏗️  Building package with uv..."
uv build

# Check package
echo "✅ Checking package..."
uv tool run twine check dist/*

echo ""
echo "🎉 Package ready for release!"
echo ""
echo "Built files:"
ls -la dist/

echo ""
echo "Next steps:"
echo "1. Push your changes: git push origin main"
echo "2. Create a GitHub release with tag v0.1.0"
echo "3. The GitHub Action will automatically publish to PyPI"
echo ""
echo "Or publish manually with:"
echo "  uv tool run twine upload dist/*" 