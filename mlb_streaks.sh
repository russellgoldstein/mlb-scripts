#!/bin/bash

# A script to find winning and losing streaks of 5+ games for all MLB teams for a given season.
# Dependencies: curl, jq

# --- Configuration ---
SEASON="2025"
START_DATE="${SEASON}-03-20" # A safe start date for the regular season
END_DATE="${SEASON}-09-30"   # End of the regular season
STREAK_THRESHOLD=5

# --- Team IDs and Names ---
declare -A TEAMS=(
    [108]="Los Angeles Angels"
    [109]="Arizona Diamondbacks"
    [110]="Baltimore Orioles"
    [111]="Boston Red Sox"
    [112]="Chicago Cubs"
    [113]="Cincinnati Reds"
    [114]="Cleveland Guardians"
    [115]="Colorado Rockies"
    [116]="Detroit Tigers"
    [117]="Houston Astros"
    [118]="Kansas City Royals"
    [119]="Los Angeles Dodgers"
    [120]="Washington Nationals"
    [121]="New York Mets"
    [133]="Oakland Athletics"
    [134]="Pittsburgh Pirates"
    [135]="San Diego Padres"
    [136]="Seattle Mariners"
    [137]="San Francisco Giants"
    [138]="St. Louis Cardinals"
    [139]="Tampa Bay Rays"
    [140]="Texas Rangers"
    [141]="Toronto Blue Jays"
    [142]="Minnesota Twins"
    [143]="Philadelphia Phillies"
    [144]="Atlanta Braves"
    [145]="Chicago White Sox"
    [146]="Miami Marlins"
    [147]="New York Yankees"
    [158]="Milwaukee Brewers"
)

# --- Function to check for dependencies ---
check_deps() {
    for cmd in curl jq; do
        if ! command -v "$cmd" &> /dev/null; then
            echo "Error: Required command '$cmd' is not installed." >&2
            echo "Please install it to continue." >&2
            exit 1
        fi
    done
}

# --- Main Logic ---

# Check for required tools first
check_deps

# Variable to hold all streaks for the final summary
ALL_STREAKS=""

# Loop through each team ID defined in the TEAMS associative array
for team_id in "${!TEAMS[@]}"; do
    team_name="${TEAMS[$team_id]}"
    echo "## Processing: ${team_name} (ID: ${team_id})"
    echo "" # Newline for cleaner output

    # Construct the API URL for the current team
    API_URL="https://statsapi.mlb.com/api/v1/schedule?lang=en&sportIds=1&season=${SEASON}&startDate=${START_DATE}&endDate=${END_DATE}&teamId=${team_id}&timeZone=America/New_York&eventTypes=primary&scheduleTypes=games&hydrate=team,game(seriesStatus)"

    # Fetch data and process it with jq
    # The jq filter does the following:
    # 1. Flattens all games from the '.dates[]' array into a single stream.
    # 2. Selects only games that are 'Final' and 'Regular Season'.
    # 3. For each game, creates a simple object with the date and whether the specified team won.
    # 4. Outputs a simple string "date result" (e.g., "2025-04-15 true") for easy parsing in bash.
    game_data=$(curl -s "$API_URL" | jq -r --argjson team_id "$team_id" '
        .dates[].games[] |
        select(.status.abstractGameState == "Final" and .gameType == "R") |
        {
            date: .officialDate,
            won: (if .teams.away.team.id == $team_id then .teams.away.isWinner else .teams.home.isWinner end)
        } |
        "\(.date) \(.won)"
    ')

    if [ -z "$game_data" ]; then
        echo "No regular season game data found for ${team_name} in the specified date range."
        echo "------------------------------------------------------------------"
        continue
    fi

    # Initialize streak tracking variables
    current_streak=0
    current_streak_type=""
    streak_start_date=""
    last_game_date=""
    team_has_streaks=false

    # Read the processed game data line by line
    while read -r date result; do
        if [ -z "$current_streak_type" ]; then
            # First game of the season for this team
            current_streak_type=$result
            current_streak=1
            streak_start_date=$date
        elif [ "$result" == "$current_streak_type" ]; then
            # Streak continues
            ((current_streak++))
        else
            # Streak is broken
            if [ "$current_streak" -ge "$STREAK_THRESHOLD" ]; then
                streak_word=$( [ "$current_streak_type" == "true" ] && echo "WIN" || echo "LOSS" )
                echo "  - ${streak_word} Streak: ${current_streak} games from ${streak_start_date} to ${last_game_date}"
                ALL_STREAKS+="${current_streak}|${streak_word}|${team_name}|${streak_start_date}|${last_game_date}\n"
                team_has_streaks=true
            fi
            # Start a new streak
            current_streak_type=$result
            current_streak=1
            streak_start_date=$date
        fi
        last_game_date=$date
    done <<< "$game_data"

    # Check for a streak that was active at the very end of the season
    if [ "$current_streak" -ge "$STREAK_THRESHOLD" ]; then
        streak_word=$( [ "$current_streak_type" == "true" ] && echo "WIN" || echo "LOSS" )
        echo "  - ${streak_word} Streak: ${current_streak} games from ${streak_start_date} to ${last_game_date}"
        ALL_STREAKS+="${current_streak}|${streak_word}|${team_name}|${streak_start_date}|${last_game_date}\n"
        team_has_streaks=true
    fi

    if [ "$team_has_streaks" = false ]; then
        echo "  No streaks of ${STREAK_THRESHOLD} or more games found."
    fi

    echo ""
    echo "------------------------------------------------------------------"
    echo ""
done

# --- Overall Summary ---
echo "## Overall Summary: Longest Streaks of 2025 (5+ Games)"
echo ""

if [ -z "$ALL_STREAKS" ]; then
    echo "No streaks of ${STREAK_THRESHOLD} or more games were found for any team."
else
    # Sort the collected streaks by length (descending) and print
    printf '%s' "$ALL_STREAKS" | sort -t'|' -k1,1nr | while IFS='|' read -r len type team start end; do
        printf "  %-25s | %4s Streak of %2d | %s to %s\n" "$team" "$type" "$len" "$start" "$end"
    done
fi
