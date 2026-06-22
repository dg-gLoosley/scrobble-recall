from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from .api import LastFmClient, LastFmError
from .recommender import RecommendationEngine
from .utils import PERIODS, load_env_file, print_table, save_recommendations

InputFunc = Callable[[str], str]
PrintFunc = Callable[..., None]

KINDS = ("tracks", "artists", "albums")
MODES = ("both", "unheard", "forgotten")


def main(project_dir: Path | None = None, *, pause_on_exit: bool = True) -> int:
    try:
        return run(project_dir or Path.cwd())
    finally:
        if pause_on_exit:
            _pause()


def run(
    project_dir: Path,
    *,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> int:
    env_path = project_dir / ".env"
    load_env_file(env_path)

    print_func()
    print_func("Scrobble Recall")
    print_func("Answer a few questions and recommendations will appear here.")
    print_func()

    api_key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not api_key:
        api_key = _prompt_required("Last.fm API key", input_func)
        if _prompt_yes_no("Save this API key in .env for next time?", default=True, input_func=input_func):
            _save_api_key(env_path, api_key)
            print_func(f"Saved API key to {env_path}")
            print_func()

    username = _prompt_required("Last.fm username", input_func)
    kind = _prompt_choice("Recommend", KINDS, default="tracks", input_func=input_func)
    mode = _prompt_choice("Recommendation mix", MODES, default="both", input_func=input_func)
    period = _prompt_choice("Listening period", PERIODS, default="overall", input_func=input_func)

    limit_label = "How many recommendations per group" if mode == "both" else "How many recommendations"
    limit = _prompt_int(limit_label, default=25, minimum=1, input_func=input_func)

    verify_new = True
    if mode in {"both", "unheard"}:
        verify_new = _prompt_yes_no(
            "Double-check that new picks have zero Last.fm plays?",
            default=True,
            input_func=input_func,
        )

    save_results = _prompt_yes_no("Save a CSV copy of the results?", default=True, input_func=input_func)
    save_path = _default_save_path(project_dir, username, kind) if save_results else None

    print_func()
    print_func("Fetching recommendations. This can take a little while...")
    print_func()

    client = LastFmClient(api_key=api_key)
    engine = RecommendationEngine(client)

    try:
        recommendations = engine.recommend(
            username,
            kind=kind,
            limit=limit,
            mode=mode,
            period=period,
            verify_new=verify_new,
        )
    except LastFmError as exc:
        print_func(f"Last.fm error: {exc}")
        return 1

    print_table(recommendations)

    if save_path is not None:
        save_recommendations(recommendations, save_path)
        print_func()
        print_func(f"Saved {len(recommendations)} recommendations to {save_path}")

    for warning in engine.warnings:
        print_func(f"Warning: {warning}")

    return 0


def _prompt_required(label: str, input_func: InputFunc) -> str:
    while True:
        value = input_func(f"{label}: ").strip()
        if value:
            return value
        print("Please enter a value.")


def _prompt_choice(
    label: str,
    options: tuple[str, ...],
    *,
    default: str,
    input_func: InputFunc,
) -> str:
    option_text = ", ".join(f"{index}. {option}" for index, option in enumerate(options, 1))
    prompt = f"{label} [{option_text}] (Enter for {default}): "
    normalized = {option.casefold(): option for option in options}

    while True:
        value = input_func(prompt).strip()
        if not value:
            return default
        if value.isdigit():
            index = int(value)
            if 1 <= index <= len(options):
                return options[index - 1]
        selected = normalized.get(value.casefold())
        if selected:
            return selected
        print(f"Please choose one of: {', '.join(options)}.")


def _prompt_int(
    label: str,
    *,
    default: int,
    minimum: int,
    input_func: InputFunc,
) -> int:
    while True:
        value = input_func(f"{label} (Enter for {default}): ").strip()
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            print("Please enter a whole number.")
            continue
        if parsed >= minimum:
            return parsed
        print(f"Please enter {minimum} or higher.")


def _prompt_yes_no(
    label: str,
    *,
    default: bool,
    input_func: InputFunc,
) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        value = input_func(f"{label} [{suffix}]: ").strip().casefold()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def _default_save_path(project_dir: Path, username: str, kind: str) -> Path:
    export_dir = project_dir / "exports"
    safe_username = _safe_filename(username) or "listener"
    base_path = export_dir / f"{safe_username}-{kind}.csv"
    if not base_path.exists():
        return base_path

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return export_dir / f"{safe_username}-{kind}-{timestamp}.csv"


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value).strip("-")


def _save_api_key(path: Path, api_key: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated = False
    output: list[str] = []

    for line in lines:
        if line.strip().startswith("LASTFM_API_KEY="):
            output.append(f"LASTFM_API_KEY={api_key}")
            updated = True
        else:
            output.append(line)

    if not updated:
        output.append(f"LASTFM_API_KEY={api_key}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _pause() -> None:
    try:
        input("\nPress Enter to close this window...")
    except EOFError:
        pass
