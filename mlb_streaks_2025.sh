#!/bin/bash

# A script to find winning and losing streaks of 5+ games for all MLB teams
# for a given season and write them to a CSV file.
# Usage: ./mlb_streaks_2025.sh [SEASON]
# Dependencies: curl, jq

# --- Configuration ---
SEASON="${1:-2025}" # Accept season as first arg, default to 2025
START_DATE="${SEASON}-03-01" # A safe start date for the regular season
END_DATE="${SEASON}-10-05"   # End of the regular season
STREAK_THRESHOLD=5
OUTPUT_FILE="mlb_streaks_${SEASON}.csv"

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

# --- Fetch team metadata ---
TEAMS_ENDPOINT="https://statsapi.mlb.com/api/v1/teams?season=${SEASON}&sportId=1"

if ! teams_response=$(curl -sf "$TEAMS_ENDPOINT"); then
    echo "Error: Failed to fetch team list for season ${SEASON}." >&2
    exit 1
fi

if ! team_lines=$(echo "$teams_response" | jq -r '.teams[] | select(.active == true) | "\(.id)|\(.name)"'); then
    echo "Error: Failed to parse team list for season ${SEASON}." >&2
    exit 1
fi

TEAM_ENTRIES=()
while IFS= read -r team_entry; do
    [ -n "$team_entry" ] && TEAM_ENTRIES+=("$team_entry")
done < <(printf '%s\n' "$team_lines" | sort)

if [ "${#TEAM_ENTRIES[@]}" -eq 0 ]; then
    echo "Error: No active teams found for season ${SEASON}." >&2
    exit 1
fi

# Create CSV file and write header
echo "Team,StreakType,Length,StartDate,EndDate" > "$OUTPUT_FILE"

# Loop through each active team returned by the API
for team_entry in "${TEAM_ENTRIES[@]}"; do
    IFS='|' read -r team_id team_name <<< "$team_entry"
    if [ -z "$team_id" ] || [ -z "$team_name" ]; then
        echo "## Skipping malformed team entry: ${team_entry}" >&2
        echo "------------------------------------------------------------------"
        continue
    fi
    echo "## Processing: ${team_name} (ID: ${team_id})"

    # Construct the API URL for the current team
    API_URL="https://statsapi.mlb.com/api/v1/schedule?lang=en&sportIds=1&season=${SEASON}&startDate=${START_DATE}&endDate=${END_DATE}&teamId=${team_id}&timeZone=America/New_York&eventTypes=primary&scheduleTypes=games&hydrate=team,game(seriesStatus)"

    # Fetch data for the team; bail out if the request fails
    if ! response=$(curl -sf "$API_URL"); then
        echo "  Error: Failed to fetch schedule data for ${team_name} (${SEASON})." >&2
        echo "------------------------------------------------------------------"
        continue
    fi

    # Process the response with jq
    if ! game_data=$(echo "$response" | jq -r --argjson team_id "$team_id" '
        .dates[].games[] |
        select(.status.abstractGameState == "Final" and .gameType == "R") |
        {
            date: .officialDate,
            won: (if .teams.away.team.id == $team_id then .teams.away.isWinner else .teams.home.isWinner end)
        } |
        "\(.date) \(.won)"
    '); then
        echo "  Error: Failed to parse schedule data for ${team_name} (${SEASON})." >&2
        echo "------------------------------------------------------------------"
        continue
    fi

    if [ -z "$game_data" ]; then
        echo "  No regular season game data found for ${team_name}."
        echo "------------------------------------------------------------------"
        continue
    fi

    # Initialize streak tracking variables
    current_streak=0
    current_streak_type=""
    streak_start_date=""
    last_game_date=""

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
                # Write the found streak to the CSV file
                echo "${team_name},${streak_word},${current_streak},${streak_start_date},${last_game_date}" >> "$OUTPUT_FILE"
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
        # Write the final streak to the CSV file
        echo "${team_name},${streak_word},${current_streak},${streak_start_date},${last_game_date}" >> "$OUTPUT_FILE"
    fi

    echo "------------------------------------------------------------------"
done

echo ""
echo "Processing complete."
echo "All streaks of ${STREAK_THRESHOLD}+ games written to ${OUTPUT_FILE}"
