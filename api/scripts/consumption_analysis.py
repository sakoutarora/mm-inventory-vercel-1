import pandas as pd
import argparse
import os
import json

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate per-day consumption for items updated during the last N days."
    )
    parser.add_argument(
        "--path",
        type=str,
        default='output.json',
        help="Consumption pattern json",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    path = args.path
    print("File path is", path)
    if not os.path.exists(path):
        raise SystemExit(f"File {path} does not exist.")
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data['results'])
    print(df[df['estimatedInventoryDaysLeft'] <= 3][['name', 'itemId', 'estimatedInventoryDaysLeft']])
    

if __name__ == "__main__":
    main()