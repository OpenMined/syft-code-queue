#!/bin/bash
set -e

echo "🚀 Starting analysis job..."

# Install dependencies
if [ -f requirements.txt ]; then
    echo "📦 Installing requirements..."
    pip install -r requirements.txt
fi

# Run the analysis
echo "🔍 Running analysis..."
python analyze.py

echo "✅ Job completed successfully!"
