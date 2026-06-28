"""
Konwersja playlisty Spotify na pobieranie teledysków z YouTube.

Pobiera listę utworów z playlisty Spotify (przez Spotify Web API lub scraping),
wyszukuje każdy utwór na YouTube i pobiera teledysk.

Użycie:
    python spotify_to_yt.py "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
    python spotify_to_yt.py "URL" --audio-only
    python spotify_to_yt.py "URL" --list-only

Wymaga:
    pip install spotipy   (Spotify Web API wrapper)
    Lub: pip install requests beautifulsoup4   (scraping publicznych playlist)

Konfiguracja Spotify API (w .env):
    SPOTIFY_CLIENT_ID=twoj_client_id
    SPOTIFY_CLIENT_SECRET=twoj_client_secret

    Wygeneruj na: https://developer.spotify.com/dashboard
"""

import subprocess
import json
import sys
import os
import time
import argparse
import re

# ============ ŁADOWANIE .env ============

def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

# ============ USTAWIENIA ============

DEFAULT_OUTPUT_DIR = "."
DEFAULT_ARCHIVE_FILE = "pobrane.txt"
FFMPEG_LOCATION = "."
FORMAT_VIDEO = "bestvideo+bestaudio/best"
FORMAT_AUDIO = "bestaudio/best"
MERGE_FORMAT = "mkv"
AUDIO_FORMAT = "mp3"
SUB_LANGS = "pl,en"
DEFAULT_DELAY = 2

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")


# ============ SPOTIFY API ============

def get_spotify_tracks_api(playlist_url: str) -> list[dict]:
    """
    Pobiera listę utworów z playlisty Spotify przez oficjalne API.
    Wymaga: pip install spotipy
    """
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError:
        print("[BŁĄD] Brak modułu spotipy. Zainstaluj: pip install spotipy")
        print("       Lub użyj trybu --no-api (scraping publicznych playlist)")
        return []

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("[BŁĄD] Brak SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET w .env")
        print("       Wygeneruj na: https://developer.spotify.com/dashboard")
        return []

    # Wyciągnij ID playlisty z URL
    playlist_id = extract_spotify_id(playlist_url)
    if not playlist_id:
        print(f"[BŁĄD] Nie rozpoznano URL Spotify: {playlist_url}")
        return []

    print(f"[INFO] Pobieranie playlisty Spotify (API)...")
    print(f"       Playlist ID: {playlist_id}")

    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))

    tracks = []
    offset = 0

    while True:
        results = sp.playlist_items(playlist_id, offset=offset, limit=100,
                                     fields="items(track(name,artists(name),duration_ms)),next")
        for item in results.get("items", []):
            track = item.get("track")
            if not track:
                continue
            title = track.get("name", "")
            artists = ", ".join(a["name"] for a in track.get("artists", []))
            duration_ms = track.get("duration_ms", 0)

            tracks.append({
                "artist": artists,
                "title": title,
                "query": f"{artists} - {title}",
                "duration_s": duration_ms // 1000,
            })

        if not results.get("next"):
            break
        offset += 100

    print(f"[INFO] Znaleziono {len(tracks)} utworów na Spotify.")
    return tracks


def get_spotify_tracks_scrape(playlist_url: str) -> list[dict]:
    """
    Fallback: pobiera publiczną playlistę Spotify przez scraping embed page.
    Nie wymaga klucza API, ale działa tylko z publicznymi playlistami.
    Wymaga: pip install requests beautifulsoup4
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        print("[BŁĄD] Brak modułów. Zainstaluj: pip install requests beautifulsoup4")
        return []

    playlist_id = extract_spotify_id(playlist_url)
    if not playlist_id:
        print(f"[BŁĄD] Nie rozpoznano URL: {playlist_url}")
        return []

    print(f"[INFO] Scraping playlisty Spotify (embed)...")
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"

    resp = requests.get(embed_url)
    if resp.status_code != 200:
        print(f"[BŁĄD] Status {resp.status_code} — playlista prywatna?")
        return []

    # Parsuj JSON z resource w HTML
    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})

    if not script_tag:
        print("[BŁĄD] Nie udało się sparsować strony Spotify.")
        return []

    try:
        data = json.loads(script_tag.string)
        # Nawigacja po strukturze danych Spotify embed
        tracks_data = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {}).get("trackList", [])

        tracks = []
        for t in tracks_data:
            title = t.get("title", "")
            subtitle = t.get("subtitle", "")  # artysta
            duration_ms = t.get("duration", 0)
            tracks.append({
                "artist": subtitle,
                "title": title,
                "query": f"{subtitle} - {title}",
                "duration_s": duration_ms // 1000,
            })
        print(f"[INFO] Scraping znalazł {len(tracks)} utworów.")
        return tracks
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"[BŁĄD] Parsowanie nie powiodło się: {e}")
        return []


def extract_spotify_id(url: str) -> str:
    """Wyciąga ID playlisty ze Spotify URL."""
    # https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=xxx
    match = re.search(r"playlist/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else ""


# ============ WYSZUKIWANIE NA YOUTUBE ============

def search_youtube(query: str) -> dict | None:
    """Szuka na YouTube i zwraca pierwszy wynik."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        f"ytsearch1:{query} official music video",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=30)
        if result.returncode != 0:
            return None

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            video_id = entry.get("id", "")
            title = entry.get("title", "")
            url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
            if not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"
            return {"id": video_id, "title": title, "url": url}
    except Exception:
        return None

    return None


# ============ POBIERANIE ============

def download_video(video_url: str, output_dir: str, archive_path: str, audio_only=False) -> bool:
    """Pobiera pojedynczy film."""
    fmt = FORMAT_AUDIO if audio_only else FORMAT_VIDEO
    cmd = ["yt-dlp", "-f", fmt, "--download-archive", archive_path,
           "--write-subs", "--sub-langs", SUB_LANGS, "--embed-subs",
           "--ffmpeg-location", FFMPEG_LOCATION, "--no-playlist",
           "--output", os.path.join(output_dir, "%(title)s [%(id)s].%(ext)s"),
           video_url]

    if not audio_only:
        cmd.extend(["--merge-output-format", MERGE_FORMAT])
    else:
        cmd.extend(["--extract-audio", "--audio-format", AUDIO_FORMAT])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=1800)
        if result.returncode == 0:
            return True
        if result.stdout and "has already been recorded" in result.stdout:
            return True
        return False
    except Exception:
        return False


def is_in_archive(video_id: str, archive_path: str) -> bool:
    if not os.path.exists(archive_path):
        return False
    with open(archive_path, "r", encoding="utf-8") as f:
        for line in f:
            if video_id in line:
                return True
    return False


# ============ ARGPARSE ============

def parse_args():
    parser = argparse.ArgumentParser(
        description="Spotify → YouTube: pobierz teledyski z playlisty Spotify"
    )
    parser.add_argument("url", help="URL playlisty Spotify")
    parser.add_argument("--output-dir", "-o", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archive", "-a", default=DEFAULT_ARCHIVE_FILE)
    parser.add_argument("--delay", "-d", type=int, default=DEFAULT_DELAY)
    parser.add_argument("--audio-only", action="store_true",
                        help="Pobieraj tylko audio (MP3)")
    parser.add_argument("--list-only", action="store_true",
                        help="Wyświetl znalezione utwory bez pobierania")
    parser.add_argument("--no-api", action="store_true",
                        help="Użyj scrapingu zamiast Spotify API")
    return parser.parse_args()


# ============ MAIN ============

def main():
    args = parse_args()

    print("=" * 60)
    print(" Spotify → YouTube Downloader")
    print("=" * 60)
    print()

    # Krok 1: Pobierz listę z Spotify
    if args.no_api:
        tracks = get_spotify_tracks_scrape(args.url)
    else:
        tracks = get_spotify_tracks_api(args.url)
        if not tracks:
            print("[INFO] Próbuję scraping jako fallback...")
            tracks = get_spotify_tracks_scrape(args.url)

    if not tracks:
        print("[BŁĄD] Nie udało się pobrać listy utworów ze Spotify.")
        sys.exit(1)

    # Krok 2: Wyszukaj na YouTube
    print(f"\n[INFO] Wyszukiwanie {len(tracks)} utworów na YouTube...\n")
    archive_path = os.path.abspath(args.archive)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    found = []
    not_found = []

    for i, track in enumerate(tracks, 1):
        print(f"  [{i}/{len(tracks)}] {track['query'][:55]}...", end=" ", flush=True)
        yt_result = search_youtube(track["query"])

        if yt_result:
            yt_result["spotify_query"] = track["query"]
            found.append(yt_result)
            print(f"→ {yt_result['title'][:40]}")
        else:
            not_found.append(track)
            print("✗ nie znaleziono")

        time.sleep(0.5)  # rate limiting

    print(f"\n[INFO] Znaleziono na YouTube: {len(found)}/{len(tracks)}")

    if not_found:
        print(f"[UWAGA] Nie znaleziono {len(not_found)} utworów:")
        for t in not_found[:10]:
            print(f"  - {t['query']}")
        if len(not_found) > 10:
            print(f"  ... i {len(not_found) - 10} więcej")

    # Tryb list-only
    if args.list_only:
        print(f"\nZnalezione ({len(found)}):")
        for i, entry in enumerate(found, 1):
            status = "[POBRANE]" if is_in_archive(entry["id"], archive_path) else "[NOWE]"
            print(f"  {i:3}. {status} {entry['spotify_query']}")
            print(f"       → {entry['url']}")
        return

    # Krok 3: Pobierz
    to_download = [e for e in found if not is_in_archive(e["id"], archive_path)]
    print(f"\n[INFO] Do pobrania: {len(to_download)} (pominięto {len(found) - len(to_download)} już pobranych)")

    if not to_download:
        print("[INFO] Wszystko już pobrane!")
        return

    success = 0
    failed = []

    try:
        for i, entry in enumerate(to_download, 1):
            print(f"\n[{i}/{len(to_download)}] {entry['spotify_query'][:55]}...")
            print(f"       YT: {entry['url']}")

            ok = download_video(entry["url"], output_dir, archive_path, args.audio_only)
            if ok:
                success += 1
                print(f"       ✓ OK")
            else:
                failed.append(entry)
                print(f"       ✗ BŁĄD")

            if i < len(to_download):
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print(f"\n\n[PRZERWANO] Pobrano: {success}")
        sys.exit(0)

    print(f"\n{'=' * 60}")
    print(f" PODSUMOWANIE: Pobrano {success}, Błędy {len(failed)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
