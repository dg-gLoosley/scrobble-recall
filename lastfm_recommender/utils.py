from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from .models import Recommendation

PERIODS = ("overall", "7day", "1month", "3month", "6month", "12month")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def print_table(recommendations: list[Recommendation]) -> None:
    if not recommendations:
        print("No recommendations found. Try a larger result count or a different listening period.")
        return

    rows = [_row_for(index, item) for index, item in enumerate(recommendations, 1)]
    widths = [
        max(len(str(row[column])) for row in rows + [("No.", "Type", "Artist", "Title", "Why")])
        for column in range(5)
    ]
    widths = [min(widths[0], 4), min(widths[1], 10), min(widths[2], 26), min(widths[3], 32), min(widths[4], 54)]
    header = ("No.", "Type", "Artist", "Title", "Why")
    print(_format_row(header, widths))
    print(_format_row(tuple("-" * width for width in widths), widths))
    for row in rows:
        print(_format_row(row, widths))


def save_recommendations(recommendations: list[Recommendation], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.casefold() == ".json":
        path.write_text(
            json.dumps([item.to_dict() for item in recommendations], indent=2),
            encoding="utf-8",
        )
        return

    fields = ["kind", "category", "artist", "title", "album", "score", "reason", "url"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in recommendations:
            data = item.to_dict()
            writer.writerow({field: data.get(field) for field in fields})


def _row_for(index: int, item: Recommendation) -> tuple[str, str, str, str, str]:
    label = "new" if item.category == "unheard" else "forgotten"
    artist = item.artist or ""
    title = item.title if item.kind != "artists" else ""
    return (str(index), label, artist, title, item.reason)


def _format_row(row: tuple[str, str, str, str, str], widths: list[int]) -> str:
    return " | ".join(_clip(value, width).ljust(width) for value, width in zip(row, widths))


def _clip(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."
