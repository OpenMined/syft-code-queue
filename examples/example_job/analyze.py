#!/usr/bin/env python3
"""
Example analysis script for syft-code-queue.
This demonstrates a more complex analysis workflow.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path

def main():
    print("🔬 Starting advanced privacy-safe analysis...")
    
    # Simulate loading data from the datasite
    np.random.seed(42)
    data = pd.DataFrame({
        'values': np.random.normal(50, 15, 1000),
        'category': np.random.choice(['A', 'B', 'C'], 1000)
    })
    
    print(f"📊 Loaded {len(data)} records")
    
    # Privacy-safe aggregate analysis only
    results = {
        "total_records": len(data),
        "category_stats": {
            "counts": data['category'].value_counts().to_dict(),
            "mean_by_category": data.groupby('category')['values'].mean().to_dict()
        },
        "overall_stats": {
            "mean": float(data['values'].mean()),
            "std": float(data['values'].std()),
            "median": float(data['values'].median())
        }
    }
    
    # Save results
    with open("analysis_results.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    print("�� Analysis Results:")
    print(json.dumps(results, indent=2))
    print("✅ Analysis complete!")

if __name__ == "__main__":
    main()
