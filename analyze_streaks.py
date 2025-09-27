#!/usr/bin/env python3
"""Analyze MLB streak CSV output for multiple seasons."""

from __future__ import annotations

import csv
import glob
import os
import re
from collections import defaultdict
from datetime import datetime
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


def percentile_rank(value: float, data: List[float]) -> float | None:
    if not data:
        return None
    if value is None:
        return None
    count = sum(1 for item in data if item <= value)
    return (count / len(data)) * 100


def ordinal(value: int) -> str:
    remainder = value % 100
    if 11 <= remainder <= 13:
        suffix = "th"
    else:
        last_digit = value % 10
        if last_digit == 1:
            suffix = "st"
        elif last_digit == 2:
            suffix = "nd"
        elif last_digit == 3:
            suffix = "rd"
        else:
            suffix = "th"
    return f"{value}{suffix}"


def format_percentile(value: float | None) -> str:
    if value is None:
        return "percentile unavailable"
    rounded = round(value, 1)
    if rounded.is_integer():
        return f"{ordinal(int(rounded))} percentile"
    return f"{rounded:.1f} percentile"


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
    team_sequences: Dict[int, Dict[str, List[Tuple[datetime, str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )

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

                if length >= 5:
                    start_date_str = row.get("StartDate", "")
                    if start_date_str:
                        try:
                            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                        except ValueError:
                            pass
                        else:
                            team_sequences[season][team_name].append(
                                (start_date, streak_type, length)
                            )

    swing_counts: Dict[int, Dict[Tuple[str, int], int]] = {
        threshold: defaultdict(int) for threshold in THRESHOLDS
    }

    for season, team_data in team_sequences.items():
        for team_name, entries in team_data.items():
            entries.sort(key=lambda item: item[0])
            for idx in range(len(entries) - 1):
                current_date, current_type, current_length = entries[idx]
                next_date, next_type, next_length = entries[idx + 1]

                if current_type == next_type:
                    continue

                for threshold in THRESHOLDS:
                    if current_length >= threshold and next_length >= threshold:
                        swing_counts[threshold][(team_name, season)] += 1

    print("Yearly streak counts:")
    print(
        "  Seasons with the most total streaks at or above each length, plus the "
        f"current {CURRENT_SEASON} tally for context."
    )
    for threshold in THRESHOLDS:
        counts = year_counts[threshold]
        if not counts:
            print(f"  {threshold}+: No data available")
            continue

        max_count = max(counts.values())
        winning_years = sorted(year for year, count in counts.items() if count == max_count)
        years_formatted = ", ".join(str(year) for year in winning_years)
        print(f"  {threshold}+: {years_formatted} ({max_count} streaks)")

        current_count = counts.get(CURRENT_SEASON)
        if current_count is not None:
            percentile = percentile_rank(current_count, list(counts.values()))
            print(
                f"    {CURRENT_SEASON}: {current_count} streaks "
                f"({format_percentile(percentile)})"
            )
        else:
            print(f"    {CURRENT_SEASON}: No data")

    base_threshold = THRESHOLDS[0]
    base_totals = team_streak_totals_by_threshold[base_threshold]
    if not base_totals:
        print("\nNo team streak data available for 5+ game analysis.")
        return

    print("\nHighest percentage of games in long streaks:")
    print(
        "  Highlights the team-seasons that spent the largest share of their schedule "
        "inside long streaks, alongside the current season leader."
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
            percentile = percentile_rank(current_percentage, percentage_values)
            print(
                f"    {CURRENT_SEASON} leader: {current_team} with "
                f"{current_games} of {current_season_games} games "
                f"({current_percentage:.1f}%, {format_percentile(percentile)})"
            )
        else:
            print(f"    {CURRENT_SEASON}: No data")

    print("\nBalanced win/loss streak counts:")
    print(
        "  Shows which team-seasons logged the most matched win and loss streaks of "
        "each length; ties note how many seasons share the record and the "
        f"{CURRENT_SEASON} snapshot."
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

        if current_best_key and current_best_totals and current_best_pair > 0:
            current_team, current_season_value = current_best_key
            percentile = percentile_rank(current_best_pair, pair_values)
            print(
                f"    {CURRENT_SEASON}: {current_team} in {current_season_value} with "
                f"{current_best_pair} matched streaks (wins={current_best_totals['WIN']}, "
                f"losses={current_best_totals['LOSS']}) "
                f"({format_percentile(percentile)})"
            )
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
            percentile = percentile_rank(current_max_wins, win_values)
            print(
                f"    {CURRENT_SEASON}: {current_text} ({current_max_wins} win streaks, "
                f"{format_percentile(percentile)})"
            )
        else:
            print(f"    {CURRENT_SEASON}: No win streaks recorded")

    base_threshold = THRESHOLDS[0]
    print(f"\nAsymmetry in {base_threshold}+ game streaks:")
    print(
        "  Measures how lopsided seasons were between long win and loss streaks, "
        f"including the most skewed {CURRENT_SEASON} results."
    )
    base_counts = team_win_loss_counts[base_threshold]
    if not base_counts:
        print("  No streak data available")
    else:
        positive_entries = [
            (counts["WIN"] - counts["LOSS"], counts["WIN"] + counts["LOSS"], key, counts)
            for key, counts in base_counts.items()
            if counts["WIN"] - counts["LOSS"] > 0
        ]
        negative_entries = [
            (counts["WIN"] - counts["LOSS"], counts["WIN"] + counts["LOSS"], key, counts)
            for key, counts in base_counts.items()
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
            for key, counts in base_counts.items()
            if key[1] == CURRENT_SEASON and counts["WIN"] - counts["LOSS"] > 0
        ]
        current_negative = [
            (counts["WIN"] - counts["LOSS"], counts["WIN"] + counts["LOSS"], key, counts)
            for key, counts in base_counts.items()
            if key[1] == CURRENT_SEASON and counts["WIN"] - counts["LOSS"] < 0
        ]

        if current_positive:
            diff, total, (team, season), counts = max(
                current_positive, key=lambda item: (item[0], item[1], item[2][0])
            )
            percentile = percentile_rank(diff, positive_diffs)
            print(
                f"  {CURRENT_SEASON} win-heavy: {team} (wins={counts['WIN']}, "
                f"losses={counts['LOSS']}, diff=+{diff}) "
                f"({format_percentile(percentile)})"
            )
        else:
            print(f"  {CURRENT_SEASON} win-heavy: None")

        if current_negative:
            diff, total, (team, season), counts = min(
                current_negative, key=lambda item: (item[0], -item[1], item[2][0])
            )
            percentile = percentile_rank(-diff, negative_magnitudes)
            print(
                f"  {CURRENT_SEASON} loss-heavy: {team} (wins={counts['WIN']}, "
                f"losses={counts['LOSS']}, diff={diff}) "
                f"({format_percentile(percentile)})"
            )
        else:
            print(f"  {CURRENT_SEASON} loss-heavy: None")

    print("\nRoller-coaster streak swings:")
    print(
        "  Counts back-to-back swings between long win and loss streaks for each "
        "threshold, spotlighting the most volatile seasons and the current year."
    )
    for threshold in THRESHOLDS:
        counts = swing_counts[threshold]
        if not counts:
            print(f"  {threshold}+: No swings recorded")
            continue

        swing_values = list(counts.values())

        best_key, best_value = max(
            counts.items(), key=lambda item: (item[1], item[0][1], item[0][0])
        )
        best_team, best_season = best_key
        print(
            f"  {threshold}+: {best_team} in {best_season} with {best_value} swings"
        )

        current_candidates = [
            (key, value)
            for key, value in counts.items()
            if key[1] == CURRENT_SEASON
        ]
        if current_candidates:
            current_key, current_value = max(
                current_candidates, key=lambda item: (item[1], item[0][0])
            )
            current_team, _ = current_key
            percentile = percentile_rank(current_value, swing_values)
            print(
                f"    {CURRENT_SEASON}: {current_team} with {current_value} swings "
                f"({format_percentile(percentile)})"
            )
        else:
            print(f"    {CURRENT_SEASON}: No swings recorded")


if __name__ == "__main__":
    main()
