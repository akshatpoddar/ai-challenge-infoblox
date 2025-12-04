#!/usr/bin/env python3
"""
Main entry point for inventory normalization pipeline.
Processes inventory_raw.csv and generates inventory_clean.csv and anomalies.json.
"""

import sys
from pathlib import Path

from normalize_inventory import process

HERE = Path(__file__).parent

def main():
    """Main entry point."""
    input_csv = HERE / "inventory_raw.csv"
    output_csv = HERE / "inventory_clean.csv"
    anomalies_json = HERE / "anomalies.json"
    
    if not input_csv.exists():
        print(f"Error: {input_csv} not found")
        sys.exit(1)
    
    print(f"Processing inventory data from {input_csv}...")
    process(str(input_csv), str(output_csv), str(anomalies_json))
    print("\nNormalization complete!")

if __name__ == "__main__":
    main()
