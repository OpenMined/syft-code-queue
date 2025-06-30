#!/usr/bin/env python3
"""
Sample analysis script for Syft Code Queue.
This demonstrates a more complex analysis package.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    print("🔬 Starting advanced analysis...")

    # Simulate loading data from the datasite
    # In reality, this would access the datasite's secure data
    np.random.seed(42)
    data = pd.DataFrame({
        'values': np.random.normal(50, 15, 1000),
        'category': np.random.choice(['A', 'B', 'C'], 1000),
        'timestamp': pd.date_range('2024-01-01', periods=1000, freq='1H')
    })

    print(f"📊 Loaded {len(data)} records")

    # Privacy-safe aggregate analysis only
    results = {
        "total_records": len(data),
        "time_range": {
            "start": data['timestamp'].min().isoformat(),
            "end": data['timestamp'].max().isoformat()
        },
        "category_stats": {
            "counts": data['category'].value_counts().to_dict(),
            "percentages": (data['category'].value_counts(normalize=True) * 100).to_dict()
        },
        "value_statistics": {
            "mean": float(data['values'].mean()),
            "std": float(data['values'].std()),
            "median": float(data['values'].median()),
            "min": float(data['values'].min()),
            "max": float(data['values'].max())
        },
        "category_means": data.groupby('category')['values'].mean().to_dict()
    }

    # Save results
    output_path = Path("analysis_results.json")
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"📈 Analysis complete! Results saved to {output_path}")
    print(f"   Categories analyzed: {list(results['category_stats']['counts'].keys())}")
    print(f"   Overall mean: {results['value_statistics']['mean']:.2f}")

    return results

if __name__ == "__main__":
    main()
