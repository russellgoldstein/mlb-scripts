#!/usr/bin/env python3
"""Analyze MLB streak CSV output for multiple seasons."""

from __future__ import annotations

import csv
import glob
import os
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

CSV_PATTERN = "mlb_streaks_*.csv"
SEASON_REGEX = re.compile(r"mlb_streaks_(\d{4})\.csv$")
IGNORED_SEASONS = {2020}
CURRENT_SEASON = 2025
THRESHOLDS = list(range(5, 11))
WIN_LOSS_TYPES = {"WIN", "LOSS"}
SEASON_GAME_PHASES = (
    (1900, 140),
    (1904, 154),
    (1919, 140),
    (1920, 154),
    (1962, 162),
)
RANK_TOLERANCE = 1e-9


def ordinal(value: int) -> str:
    remainder = value % 100
    if 10 <= remainder <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def compute_rank(
    value: float,
    values: List[float],
    higher_is_better: bool = True,
    tolerance: float = RANK_TOLERANCE,
) -> tuple[int, int, int]:
    if not values:
        return 0, 0, 0

    numeric_values = [float(item) for item in values]
    target = float(value)

    if higher_is_better:
        better = sum(1 for item in numeric_values if item > target + tolerance)
    else:
        better = sum(1 for item in numeric_values if item < target - tolerance)

    tied = sum(1 for item in numeric_values if abs(item - target) <= tolerance)
    return better + 1, tied, len(numeric_values)


def top_rank_annotation(
    value: float | None,
    values: List[float],
    *,
    higher_is_better: bool = True,
    top_n: int = 10,
    tolerance: float = RANK_TOLERANCE,
) -> str | None:
    if value is None or not values:
        return None

    rank, tie_count, _ = compute_rank(value, values, higher_is_better, tolerance)
    if rank == 0 or rank > top_n:
        return None

    if tie_count > 1:
        return f"tied for {ordinal(rank)} all-time"
    return f"{ordinal(rank)} all-time"
def percentile_rank(value: float, data: List[float]) -> float | None:
    if value is None or not data:
        return None
    count = sum(1 for item in data if item <= value)
    return (count / len(data)) * 100


def format_percentile(value: float | None) -> str:
    if value is None:
        return "percentile unavailable"
    return f"{value:.1f} percentile"


def _is_effectively_int(value: float) -> bool:
    return abs(value - round(value)) < 1e-9


def _format_single(value: float, as_int: bool) -> str:
    if as_int:
        return str(int(round(value)))
    return f"{value:.1f}"


def _format_range(start: float, end: float) -> str:
    return f"{start:.1f}-{end:.1f}"


def build_distribution_chart(
    values: List[float],
    highlight: float | None,
    highlight_label: str,
    highlight_percentile: float | None = None,
    width: int = 30,
    max_bins: int = 10,
    prefer_discrete: bool = False,
) -> List[str]:
    numeric_values = [float(value) for value in values]
    if not numeric_values:
        return []

    min_value = min(numeric_values)
    max_value = max(numeric_values)
    highlight_value = float(highlight) if highlight is not None else None
    as_int = all(_is_effectively_int(value) for value in numeric_values)

    unique_count = len(set(numeric_values))
    bin_count = min(max_bins, unique_count) if unique_count else 1
    if bin_count <= 0:
        bin_count = 1

    if max_value == min_value:
        bar = "#" * width
        marker = ""
        if highlight_value is not None:
            marker = f" <-- {highlight_label} {_format_single(highlight_value, as_int)}"
        header = f"{'Value':>12} | Bar (count)"
        line = (
            f"{_format_single(min_value, as_int):>12} | {bar} "
            f"({len(numeric_values)}){marker}"
        )
        return [header, line]

    discrete_mode = as_int and (prefer_discrete or unique_count <= max_bins)

    if discrete_mode:
        value_counts = Counter(numeric_values)
        sorted_values = sorted(value_counts.keys())
        max_count = max(value_counts.values()) if value_counts else 0
        lines = []
        for value in sorted_values:
            count = value_counts[value]
            if max_count == 0:
                bar_length = 0
            else:
                bar_length = int(round((count / max_count) * width))
                if count > 0 and bar_length == 0:
                    bar_length = 1
            bar = "#" * bar_length
            marker = ""
            if highlight_value is not None and abs(highlight_value - value) < 1e-9:
                marker = (
                    f" <-- {highlight_label} "
                    f"{_format_single(highlight_value, as_int)}"
                )
            if highlight_percentile is not None:
                marker += f" ({format_percentile(highlight_percentile)})"
            lines.append(f"{value:>12.1f} | {bar} ({count}){marker}")
        header = f"{'Value':>12} | Bar (count)"
        return [header] + lines

    step = (max_value - min_value) / bin_count
    if step == 0:
        step = 1.0

    bin_counts = [0] * bin_count
    for value in numeric_values:
        index = int((value - min_value) / step)
        if index >= bin_count:
            index = bin_count - 1
        if index < 0:
            index = 0
        bin_counts[index] += 1

    max_count = max(bin_counts) if bin_counts else 0
    highlight_index: int | None = None
    if highlight_value is not None:
        index = int((highlight_value - min_value) / step)
        if 0 <= index < bin_count:
            highlight_index = index
        elif highlight_value >= max_value:
            highlight_index = bin_count - 1

    lines: List[str] = []
    for position in range(bin_count):
        start = min_value + position * step
        end = (
            min_value + (position + 1) * step
            if position < bin_count - 1
            else max_value
        )
        range_label = _format_range(start, end)
        count = bin_counts[position]
        if max_count == 0:
            bar_length = 0
        else:
            bar_length = int(round((count / max_count) * width))
            if count > 0 and bar_length == 0:
                bar_length = 1
        bar = "#" * bar_length
        marker = ""
        if highlight_index == position and highlight_value is not None:
            marker = (
                f" <-- {highlight_label} "
                f"{_format_single(highlight_value, as_int)}"
            )
            if highlight_percentile is not None:
                marker += f" ({format_percentile(highlight_percentile)})"
        lines.append(f"{range_label:>12} | {bar} ({count}){marker}")

    header = f"{'Range':>12} | Bar (count)"
    return [header] + lines


def games_in_season(season: int) -> int:
    games = SEASON_GAME_PHASES[0][1]
    for start_year, total_games in SEASON_GAME_PHASES:
        if season >= start_year:
            games = total_games
        else:
            break
    return games


def find_csv_files(base_dir: str) -> List[str]:
    pattern = os.path.join(base_dir, CSV_PATTERN)
    return sorted(glob.glob(pattern))


def extract_season(filename: str) -> int | None:
    match = SEASON_REGEX.search(os.path.basename(filename))
    return int(match.group(1)) if match else None


def main() -> None:
    base_dir = os.getcwd()
    files = find_csv_files(base_dir)

    if not files:
        print("No CSV files found matching pattern 'mlb_streaks_*.csv'.")
        return

    year_counts: Dict[int, Dict[int, int]] = {threshold: defaultdict(int) for threshold in THRESHOLDS}
    team_win_loss_counts: Dict[
        int, defaultdict[Tuple[str, int], Dict[str, int]]
    ] = {threshold: defaultdict(lambda: {"WIN": 0, "LOSS": 0}) for threshold in THRESHOLDS}
    team_streak_totals_by_threshold: Dict[
        int, defaultdict[Tuple[str, int], int]
    ] = {threshold: defaultdict(int) for threshold in THRESHOLDS}

    for path in files:
        season = extract_season(path)
        if season is None:
            continue

        with open(path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    length = int(row["Length"])
                except (ValueError, KeyError):
                    continue

                team_name = row.get("Team", "Unknown Team")

                for threshold in THRESHOLDS:
                    if length >= threshold:
                        year_counts[threshold][season] += 1
                        if season not in IGNORED_SEASONS:
                            team_streak_totals_by_threshold[threshold][(team_name, season)] += length

                streak_type = row.get("StreakType", "").strip().upper()
                if streak_type not in WIN_LOSS_TYPES:
                    continue

                if season in IGNORED_SEASONS:
                    continue

                team_key = (team_name, season)
                for threshold in THRESHOLDS:
                    if length >= threshold:
                        team_win_loss_counts[threshold][team_key][streak_type] += 1

    print("Yearly streak counts:")
    print(
        "  Seasons with the most total streaks (win or loss) at or above each length, plus the "
        f"current {CURRENT_SEASON} tally for context."
    )
    for index, threshold in enumerate(THRESHOLDS):
        if index > 0:
            print()
        print(f"{threshold}+ win/loss streaks:")
        print()

        counts = year_counts[threshold]
        if not counts:
            print("* Record: No data available")
            print(f"* {CURRENT_SEASON}: No data")
            continue

        max_count = max(counts.values())
        winning_years = sorted(year for year, count in counts.items() if count == max_count)
        years_formatted = ", ".join(str(year) for year in winning_years)
        print(f"* Record: {years_formatted} ({max_count} streaks)")

        current_count = counts.get(CURRENT_SEASON)
        distribution_values = [float(value) for value in counts.values()]
        if current_count is not None:
            annotation = top_rank_annotation(float(current_count), distribution_values)
            annotation_text = f" — {annotation}" if annotation else ""
            print(f"* {CURRENT_SEASON}: {current_count} streaks{annotation_text}")
            current_percentile = percentile_rank(float(current_count), distribution_values)
            chart_lines = build_distribution_chart(
                distribution_values,
                float(current_count),
                f"{CURRENT_SEASON}",
                current_percentile,
            )
            if chart_lines:
                print("  Distribution:")
                for line in chart_lines:
                    print(f"    {line}")
        else:
            print(f"* {CURRENT_SEASON}: No data")

    base_threshold = THRESHOLDS[0]
    base_totals = team_streak_totals_by_threshold[base_threshold]
    if not base_totals:
        print("\nNo team streak data available for 5+ game analysis.")
        return

    print("\nHighest percentage of season's games in long streaks:")
    print(
        "  Highlights the team-seasons that spent the largest share of their schedule "
        "inside long streaks (win or loss)."
    )
    for threshold in THRESHOLDS:
        totals = team_streak_totals_by_threshold[threshold]
        if not totals:
            print(f"  {threshold}+: No data available")
            continue

        percentage_values = [
            (games / games_in_season(season)) * 100
            for (team, season), games in totals.items()
        ]

        best_entry = max(
            totals.items(),
            key=lambda item: (
                item[1] / games_in_season(item[0][1]),
                item[0][1],
                item[0][0],
            ),
        )
        (best_team, best_season), streak_games = best_entry
        season_games = games_in_season(best_season)
        percentage = (streak_games / season_games) * 100
        print(
            f"  {threshold}+: {best_team} in {best_season}: "
            f"{streak_games} of {season_games} games ({percentage:.1f}%)"
        )

        current_entries = [
            (team, games)
            for (team, season), games in totals.items()
            if season == CURRENT_SEASON
        ]
        if current_entries:
            current_team, current_games = max(
                current_entries, key=lambda item: (item[1], item[0])
            )
            current_season_games = games_in_season(CURRENT_SEASON)
            current_percentage = (current_games / current_season_games) * 100
            annotation = top_rank_annotation(current_percentage, percentage_values)
            annotation_text = f" — {annotation}" if annotation else ""
            print(
                f"    {CURRENT_SEASON} leader: {current_team} with "
                f"{current_games} of {current_season_games} games "
                f"({current_percentage:.1f}%){annotation_text}"
            )
            chart_lines = build_distribution_chart(
                percentage_values,
                current_percentage,
                f"{CURRENT_SEASON} %",
                percentile_rank(current_percentage, percentage_values),
            )
            if chart_lines:
                print("    Distribution:")
                for line in chart_lines:
                    print(f"      {line}")
        else:
            print(f"    {CURRENT_SEASON}: No data")

    print("\nBalanced win/loss streak counts:")
    print(
        "  Shows which team-seasons logged the most matched win AND loss streaks of "
        "each length; ties note how many team-seasons share the record."
    )
    for threshold in THRESHOLDS:
        team_counts = team_win_loss_counts[threshold]
        if not team_counts:
            print(f"  {threshold}+: No eligible win/loss pairs")
            continue

        pair_values = [min(counts["WIN"], counts["LOSS"]) for counts in team_counts.values()]

        best_pair_count = 0
        leaders: List[Tuple[Tuple[str, int], Dict[str, int]]] = []

        for key, counts in team_counts.items():
            pair_count = min(counts["WIN"], counts["LOSS"])
            if pair_count > best_pair_count:
                best_pair_count = pair_count
                leaders = [(key, counts)]
            elif pair_count == best_pair_count and pair_count > 0:
                leaders.append((key, counts))

        if best_pair_count == 0 or not leaders:
            print(f"  {threshold}+: No team recorded both win and loss streaks")
            continue

        leaders_sorted = sorted(leaders, key=lambda item: (item[0][1], item[0][0]))
        (top_team, top_season), top_counts = leaders_sorted[0]
        tie_suffix = ""
        if len(leaders_sorted) > 1:
            tie_suffix = f" [tied {len(leaders_sorted)} seasons]"

        print(
            f"  {threshold}+: {top_team} in {top_season} "
            f"(wins={top_counts['WIN']}, losses={top_counts['LOSS']})"
            f" with {best_pair_count} matched streaks{tie_suffix}"
        )

        current_candidates = [
            (key, counts)
            for key, counts in team_counts.items()
            if key[1] == CURRENT_SEASON
        ]
        current_best_key: Tuple[str, int] | None = None
        current_best_pair = 0
        current_best_totals: Dict[str, int] | None = None

        for key, counts in current_candidates:
            pair_count = min(counts["WIN"], counts["LOSS"])
            if pair_count > current_best_pair:
                current_best_pair = pair_count
                current_best_key = key
                current_best_totals = counts

        distribution_values = [float(value) for value in pair_values]
        if current_best_key and current_best_totals and current_best_pair > 0:
            current_team, current_season_value = current_best_key
            annotation = top_rank_annotation(float(current_best_pair), distribution_values)
            annotation_text = f" — {annotation}" if annotation else ""
            print(
                f"    {CURRENT_SEASON}: {current_team} in {current_season_value} with "
                f"{current_best_pair} matched streaks (wins={current_best_totals['WIN']}, "
                f"losses={current_best_totals['LOSS']}){annotation_text}"
            )
            chart_lines = build_distribution_chart(
                distribution_values,
                float(current_best_pair),
                f"{CURRENT_SEASON}",
                percentile_rank(float(current_best_pair), distribution_values),
                prefer_discrete=True,
            )
            if chart_lines:
                print("    Distribution:")
                for line in chart_lines:
                    print(f"      {line}")
        else:
            print(f"    {CURRENT_SEASON}: No matched win/loss streaks")

    print("\nWin streak dominance across thresholds:")
    print(
        "  Identifies the teams with the most win streaks at each length and "
        "highlights the current season leaders."
    )
    for threshold in THRESHOLDS:
        team_counts = team_win_loss_counts[threshold]
        if not team_counts:
            print(f"  {threshold}+: No data available")
            continue

        max_wins = 0
        leaders: List[Tuple[str, int]] = []
        win_values = [counts["WIN"] for counts in team_counts.values()]

        for key, counts in team_counts.items():
            win_count = counts["WIN"]
            if win_count > max_wins:
                max_wins = win_count
                leaders = [key]
            elif win_count == max_wins and win_count > 0:
                leaders.append(key)

        if max_wins == 0 or not leaders:
            print(f"  {threshold}+: No win streaks recorded")
            print(f"    {CURRENT_SEASON}: No win streaks recorded")
            continue

        leaders_sorted = sorted(leaders, key=lambda item: (item[1], item[0]))
        leader_text = ", ".join(f"{team} in {season}" for team, season in leaders_sorted)
        print(f"  {threshold}+: {leader_text} ({max_wins} win streaks)")

        current_max_wins = 0
        current_leaders: List[Tuple[str, int]] = []
        for key, counts in team_counts.items():
            team, season = key
            if season != CURRENT_SEASON:
                continue
            win_count = counts["WIN"]
            if win_count > current_max_wins:
                current_max_wins = win_count
                current_leaders = [key]
            elif win_count == current_max_wins and win_count > 0:
                current_leaders.append(key)

        if current_max_wins > 0 and current_leaders:
            current_leaders.sort(key=lambda item: item[0])
            current_text = ", ".join(team for team, _ in current_leaders)
            distribution_values = [float(value) for value in win_values]
            annotation = top_rank_annotation(float(current_max_wins), distribution_values)
            annotation_text = f" — {annotation}" if annotation else ""
            print(
                f"    {CURRENT_SEASON}: {current_text} ({current_max_wins} win streaks){annotation_text}"
            )
            chart_lines = build_distribution_chart(
                distribution_values,
                float(current_max_wins),
                f"{CURRENT_SEASON}",
                percentile_rank(float(current_max_wins), distribution_values),
                prefer_discrete=True,
            )
            if chart_lines:
                print("    Distribution:")
                for line in chart_lines:
                    print(f"      {line}")
        else:
            print(f"    {CURRENT_SEASON}: No win streaks recorded")

    for threshold in THRESHOLDS:
        print(f"\nAsymmetry in {threshold}+ game streaks:")
        print(
            "  Measures how lopsided seasons were between long win and loss streaks, "
            f"including the most skewed {CURRENT_SEASON} results."
        )
        threshold_counts = team_win_loss_counts[threshold]
        if not threshold_counts:
            print("  No streak data available")
            continue

        positive_entries = [
            (counts["WIN"] - counts["LOSS"], counts["WIN"] + counts["LOSS"], key, counts)
            for key, counts in threshold_counts.items()
            if counts["WIN"] - counts["LOSS"] > 0
        ]
        negative_entries = [
            (counts["WIN"] - counts["LOSS"], counts["WIN"] + counts["LOSS"], key, counts)
            for key, counts in threshold_counts.items()
            if counts["WIN"] - counts["LOSS"] < 0
        ]

        positive_diffs = [entry[0] for entry in positive_entries]
        negative_magnitudes = [-entry[0] for entry in negative_entries]

        if positive_entries:
            diff, total, (team, season), counts = max(
                positive_entries, key=lambda item: (item[0], item[1], item[2][1], item[2][0])
            )
            print(
                f"  Biggest win-heavy season: {team} in {season} "
                f"(wins={counts['WIN']}, losses={counts['LOSS']}, diff=+{diff})"
            )
        else:
            print("  No seasons skewed toward win streaks")

        if negative_entries:
            diff, total, (team, season), counts = min(
                negative_entries, key=lambda item: (item[0], -item[1], item[2][1], item[2][0])
            )
            print(
                f"  Biggest loss-heavy season: {team} in {season} "
                f"(wins={counts['WIN']}, losses={counts['LOSS']}, diff={diff})"
            )
        else:
            print("  No seasons skewed toward loss streaks")

        current_positive = [
            (counts["WIN"] - counts["LOSS"], counts["WIN"] + counts["LOSS"], key, counts)
            for key, counts in threshold_counts.items()
            if key[1] == CURRENT_SEASON and counts["WIN"] - counts["LOSS"] > 0
        ]
        current_negative = [
            (counts["WIN"] - counts["LOSS"], counts["WIN"] + counts["LOSS"], key, counts)
            for key, counts in threshold_counts.items()
            if key[1] == CURRENT_SEASON and counts["WIN"] - counts["LOSS"] < 0
        ]

        if current_positive:
            diff, total, (team, season), counts = max(
                current_positive, key=lambda item: (item[0], item[1], item[2][0])
            )
            distribution_values = [float(value) for value in positive_diffs]
            annotation = top_rank_annotation(float(diff), distribution_values)
            annotation_text = f" — {annotation}" if annotation else ""
            print(
                f"  {CURRENT_SEASON} win-heavy: {team} (wins={counts['WIN']}, "
                f"losses={counts['LOSS']}, diff=+{diff}){annotation_text}"
            )
            chart_lines = build_distribution_chart(
                distribution_values,
                float(diff),
                f"{CURRENT_SEASON} diff",
                percentile_rank(float(diff), distribution_values),
                prefer_discrete=True,
            )
            if chart_lines:
                print("  Distribution (win-heavy):")
                for line in chart_lines:
                    print(f"    {line}")
        else:
            print(f"  {CURRENT_SEASON} win-heavy: None")

        if current_negative:
            diff, total, (team, season), counts = min(
                current_negative, key=lambda item: (item[0], -item[1], item[2][0])
            )
            distribution_values = [float(value) for value in negative_magnitudes]
            annotation = top_rank_annotation(float(-diff), distribution_values)
            annotation_text = f" — {annotation}" if annotation else ""
            print(
                f"  {CURRENT_SEASON} loss-heavy: {team} (wins={counts['WIN']}, "
                f"losses={counts['LOSS']}, diff={diff}){annotation_text}"
            )
            chart_lines = build_distribution_chart(
                distribution_values,
                float(-diff),
                f"{CURRENT_SEASON} |diff|",
                percentile_rank(float(-diff), distribution_values),
                prefer_discrete=True,
            )
            if chart_lines:
                print("  Distribution (loss-heavy):")
                for line in chart_lines:
                    print(f"    {line}")
        else:
            print(f"  {CURRENT_SEASON} loss-heavy: None")


if __name__ == "__main__":
    main()
