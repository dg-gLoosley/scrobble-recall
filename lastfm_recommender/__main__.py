from pathlib import Path

from .interactive import main


if __name__ == "__main__":
    raise SystemExit(main(project_dir=Path.cwd()))
