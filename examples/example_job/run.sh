#!/bin/bash
set -e

echo "🚀 Starting job execution..."

# Install dependencies
if [ -f requirements.txt ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the analysis
echo "🔍 Running analysis..."
python analyze.py

echo "🎉 Job completed successfully!"
