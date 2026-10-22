"""CLI: python highs_data.py [--us-only | --india-only]"""
import argparse
import sys

from stockmonitor import job


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--us-only", action="store_true")
    g.add_argument("--india-only", action="store_true")
    a = p.parse_args()
    markets = ["US"] if a.us_only else ["IN"] if a.india_only else ["US", "IN"]
    return job.run(markets)


if __name__ == "__main__":
    sys.exit(main())
