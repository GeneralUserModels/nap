"""Master runner for all data preparation scripts."""
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def run_script(name: str):
    script = SCRIPTS_DIR / name
    print(f"\n{'='*60}")
    print(f"Running {name}...")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(SCRIPTS_DIR.parent),
    )
    if result.returncode != 0:
        print(f"ERROR: {name} failed with code {result.returncode}")
        sys.exit(1)


def main():
    run_script("prepare_demo1.py")
    run_script("prepare_demo2.py")
    run_script("prepare_demo3.py")
    print(f"\n{'='*60}")
    print("All data preparation complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
