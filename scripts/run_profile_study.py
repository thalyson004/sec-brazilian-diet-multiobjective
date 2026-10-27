"""Run the complete profile study from any working directory."""

from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

if __name__ == "__main__":
    from sec_diet.profile_pipeline import main
    raise SystemExit(main())
