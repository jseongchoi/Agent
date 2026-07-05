from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def read_table(path: str, max_rows: int) -> pd.DataFrame:
    table_path = Path(path).expanduser().resolve()
    suffix = table_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(table_path, nrows=max_rows)
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(table_path, sep="\t", nrows=max_rows)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(table_path, nrows=max_rows)
    raise ValueError(f"Unsupported data file type: {table_path.suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal semicon-agent table parser.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--max-rows", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = read_table(args.path, args.max_rows)
    df.to_pickle(args.output)


if __name__ == "__main__":
    main()
