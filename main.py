from pathlib import Path

from lastfm_recommender.interactive import main as interactive_main


if __name__ == "__main__":
    raise SystemExit(interactive_main(project_dir=Path(__file__).resolve().parent))
