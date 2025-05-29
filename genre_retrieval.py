import requests
import time
import json

def get_icon_genre(title: str, title_id: str, genre_mappings: dict[str, str], genre_weights: dict[str, int]) -> str:

    if title_id.startswith("NPXS"):
        print(f"Icon ID '{title_id}' starts with 'NPXS'. Skipping genre retrieval.")
        return "Playstation"

    if title_id.startswith("PSPEMU"):
        print(f"Icon ID '{title_id}' starts with 'PSPEMU'. Skipping genre retrieval.")
        return "PSP"

    if not title_id.startswith("PCS"):
        print(f"Icon ID '{title_id}' does not start with 'PCS' and is thus a homebrew. Skipping genre retrieval.")
        return "Homebrew"

    if not title:
        print(f"Icon ID '{title_id}' has no title. Skipping genre retrieval.")
        return "Other"

    return _get_giant_bomb_genre(title, genre_mappings, genre_weights)

def get_genre_mappings() -> dict[str, str]:
    try:
        with open("giant_bomb_genre_mappings.json", "r") as f:
            genre_mappings: dict[str, str] = json.load(f)
            print("✅ Loaded available genres from giant_bomb_genre_mappings.json.")
            return genre_mappings
    except FileNotFoundError:
        print("❌ giant_bomb_genre_mappings.json file not found. Cannot continue.")
        return {}

def get_genre_weights() -> dict[str, int]:
    try:
        with open("genre_weights.json", "r") as f:
            genre_weights: dict[str, int] = json.load(f)
            print("✅ Loaded genre weights from genre_weights.json.")
            return genre_weights
    except FileNotFoundError:
        print("❌ genre_weights.json file not found. Cannot continue.")
        return

def _get_giant_bomb_genre(title: str, genre_mappings: dict[str, str], genre_weights: dict[str, int]) -> str:
    # Read API key from file
    try:
        with open("giantbomb_api", "r") as f:
            api_key = f.read().strip()
    except FileNotFoundError:
        print("❌ API key file 'giantbomb_api' not found.")
        return "Other"

    time.sleep(1)

    # Search GiantBomb for the game title
    url = f"https://www.giantbomb.com/api/search/?api_key={api_key}"
    params = {
        "format": "json",
        "query": title,
        "resources": "game",
        "field_list": "guid",
        "limit": 1
    }
    headers = {"User-Agent": "PS Vita App DB Organizer"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        # Extract guid from the first result
        if "results" in data and data["results"]:
            guid = data["results"][0].get("guid", None)
            if guid:
                
                # Use the genre endpoint to retrieve the genre
                game_url = f"https://www.giantbomb.com/api/game/{guid}/?api_key={api_key}"
                game_params = {"format": "json", "field_list": "genres"}
                try:
                    game_response = requests.get(game_url, headers=headers, params=game_params)
                    game_response.raise_for_status()
                    game_data = game_response.json()

                    # Extract genre name and map it to predefined genres
                    if "results" in game_data and game_data["results"] and game_data["results"]["genres"]:
                        genre_names = [g["name"] for g in game_data["results"]["genres"]]

                        if genre_names:
                            mapped_genres = [genre_mappings[g] if g in genre_mappings else g for g in genre_names]
                            sorted_genres = sorted(mapped_genres, key=lambda g: genre_weights.get(g, 0), reverse=True)
                            print(f"✅ Found genre for title '{title}': {sorted_genres[0]}")
                            return sorted_genres[0]

                except requests.RequestException as e:
                    print(f"❌ Error retrieving genre for title '{title}': {e}")

    except requests.RequestException as e:
        print(f"❌ Error retrieving GiantBomb game guid for title '{title}': {e}")
    
    print("ℹ️ No genre found for title '{title_id}'. Using 'Other'.")
    return "Other"