"""
Skrypt do pobierania pełnej playlisty YouTube (>100 filmów).

Obejście limitu 100 pozycji w yt-dlp:
1. Pobieramy listę URL-i z playlisty za pomocą --flat-playlist
   (jeśli to nie zadziała dla >100, przełączamy na YouTube Data API)
2. Pobieramy każdy film osobno z yt-dlp

Użycie:
    python download_playlist.py <URL_PLAYLISTY>
    python download_playlist.py "https://www.youtube.com/playlist?list=PLxxxxx"
    python download_playlist.py "URL" --cookies cookies.txt

    Opcjonalne argumenty:
        --output-dir ŚCIEŻKA   Katalog docelowy (domyślnie: aktualny)
        --archive PLIK         Plik archiwum (domyślnie: pobrane.txt)
        --delay SEKUNDY        Opóźnienie między pobieraniami (domyślnie: 2)
        --cookies PLIK         Plik cookies (dla niepublicznych playlist)
        --cookies-from-browser NAZWA  Pobierz cookies z przeglądarki (chrome/firefox/edge)
        --use-api              Użyj YouTube Data API zamiast flat-playlist
        --api-key KLUCZ        Klucz YouTube Data API v3

Konfiguracja:
    Można też edytować sekcję DOMYŚLNE USTAWIENIA poniżej.
"""

import subprocess
import json
import sys
import os
import time
import argparse

# ============ DOMYŚLNE USTAWIENIA ============

DEFAULT_OUTPUT_DIR = "."  # katalog docelowy na pliki
DEFAULT_ARCHIVE_FILE = "pobrane.txt"  # plik archiwum (pomijanie już pobranych)
FFMPEG_LOCATION = "."  # ścieżka do ffmpeg

# Opcje pobierania
FORMAT = "bestvideo+bestaudio/best"
MERGE_FORMAT = "mkv"
SUB_LANGS = "pl,en"

# Opóźnienie między pobieraniami (sekundy) — zmniejsza ryzyko throttlingu
DEFAULT_DELAY = 2

# YouTube Data API (opcjonalnie, jeśli --flat-playlist zwraca max 100)
# Wygeneruj klucz: https://console.cloud.google.com/apis/credentials
# Włącz: YouTube Data API v3
DEFAULT_API_KEY = ""  # wpisz swój klucz API jeśli chcesz używać domyślnie

# ============ KONIEC USTAWIEŃ ============


def get_playlist_entries_ytdlp(playlist_url: str, cookies_file: str = None, cookies_from_browser: str = None) -> list[dict]:
    """
    Pobiera listę filmów z playlisty za pomocą yt-dlp --flat-playlist.
    Jeśli zwraca dokładnie 100 — próbuje pobrać w partiach (paginacja).
    Zwraca listę słowników z kluczami: id, url, title.
    """
    print(f"[INFO] Pobieranie listy filmów z playlisty (yt-dlp --flat-playlist)...")
    print(f"       URL: {playlist_url}")

    # Najpierw próba pobrania całej listy
    entries = _fetch_flat_playlist(playlist_url, cookies_file, cookies_from_browser)

    # Jeśli dostaliśmy dokładnie 100 — prawdopodobnie limit.
    # Próbujemy pobrać w partiach po 50 z --playlist-start/--playlist-end
    if len(entries) == 100:
        print("[INFO] Wykryto limit 100 pozycji. Próbuję pobrać w partiach...")
        entries = _fetch_playlist_in_batches(playlist_url, cookies_file, cookies_from_browser)

    print(f"[INFO] Znaleziono {len(entries)} filmów na playliście.")
    return entries


def _fetch_flat_playlist(playlist_url: str, cookies_file: str = None, cookies_from_browser: str = None,
                         start: int = None, end: int = None) -> list[dict]:
    """Pomocnicza: pobiera wpisy z playlisty (opcjonalnie zakres)."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
    ]

    if cookies_file:
        cmd.extend(["--cookies", cookies_file])
    elif cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])

    if start is not None:
        cmd.extend(["--playlist-start", str(start)])
    if end is not None:
        cmd.extend(["--playlist-end", str(end)])

    cmd.append(playlist_url)

    entries = []

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )

        if result.returncode != 0:
            # Nie loguj błędu jeśli to partia poza zakresem
            if start and "is not in the playlist" not in result.stderr:
                print(f"[BŁĄD] yt-dlp --flat-playlist zakończył się kodem {result.returncode}")
                print(f"       stderr: {result.stderr[:500]}")
            return []

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                video_id = entry.get("id", "")
                title = entry.get("title", "Bez tytułu")
                url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"

                if not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={url}"

                entries.append({
                    "id": video_id,
                    "title": title,
                    "url": url,
                })
            except json.JSONDecodeError:
                continue

    except subprocess.TimeoutExpired:
        print("[BŁĄD] Timeout przy pobieraniu listy playlisty (300s)")
        return []
    except FileNotFoundError:
        print("[BŁĄD] yt-dlp nie znaleziony. Upewnij się, że jest w PATH lub aktualnym katalogu.")
        return []

    return entries


def _fetch_playlist_in_batches(playlist_url: str, cookies_file: str = None, cookies_from_browser: str = None) -> list[dict]:
    """
    Pobiera playlistę w partiach po 50, żeby obejść limit 100.
    Kontynuuje aż partia zwróci 0 wyników.
    """
    all_entries = []
    seen_ids = set()
    batch_size = 50
    start = 1

    while True:
        end = start + batch_size - 1
        print(f"       Partia {start}-{end}...", end=" ")

        batch = _fetch_flat_playlist(playlist_url, cookies_file, cookies_from_browser, start=start, end=end)

        # Deduplikacja
        new_entries = []
        for entry in batch:
            if entry["id"] not in seen_ids:
                seen_ids.add(entry["id"])
                new_entries.append(entry)

        all_entries.extend(new_entries)
        print(f"({len(new_entries)} nowych)")

        # Jeśli partia zwróciła mniej niż batch_size — koniec playlisty
        if len(batch) < batch_size:
            break

        start += batch_size

        # Bezpieczeństwo — max 2000 filmów
        if start > 2000:
            print("[UWAGA] Przekroczono 2000 pozycji, przerywam.")
            break

    return all_entries


def get_playlist_entries_api(playlist_url: str, api_key: str) -> list[dict]:
    """
    Pobiera listę filmów przez YouTube Data API v3.
    Obsługuje paginację (pageToken), więc nie ma limitu 100.

    Wymaga: pip install requests
    """
    import requests

    # Wyciągnij ID playlisty z URL
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(playlist_url)
    params = parse_qs(parsed.query)
    playlist_id = params.get("list", [None])[0]

    if not playlist_id:
        print("[BŁĄD] Nie można wyciągnąć ID playlisty z URL.")
        return []

    print(f"[INFO] Pobieranie listy filmów przez YouTube Data API...")
    print(f"       Playlist ID: {playlist_id}")

    entries = []
    base_url = "https://www.googleapis.com/youtube/v3/playlistItems"
    page_token = None

    while True:
        req_params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            req_params["pageToken"] = page_token

        resp = requests.get(base_url, params=req_params)
        if resp.status_code != 200:
            print(f"[BŁĄD] YouTube API zwróciło status {resp.status_code}: {resp.text[:300]}")
            break

        data = resp.json()
        for item in data.get("items", []):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            title = snippet.get("title", "Bez tytułu")

            # Pomijaj usunięte/prywatne filmy
            if title in ("Deleted video", "Private video"):
                continue

            entries.append({
                "id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    print(f"[INFO] YouTube API zwróciło {len(entries)} filmów.")
    return entries


def is_already_downloaded(video_id: str, archive_path: str) -> bool:
    """Sprawdza, czy film jest już w pliku archiwum."""
    if not os.path.exists(archive_path):
        return False

    with open(archive_path, "r", encoding="utf-8") as f:
        for line in f:
            # Format archiwum yt-dlp: "youtube VIDEO_ID"
            if video_id in line:
                return True
    return False


def download_video(video_url: str, output_dir: str, archive_path: str, cookies_file: str = None, cookies_from_browser: str = None) -> bool:
    """
    Pobiera pojedynczy film za pomocą yt-dlp.
    Zwraca True jeśli pobrano / pominięto pomyślnie, False przy błędzie.
    """
    cmd = [
        "yt-dlp",
        "-f", FORMAT,
        "--merge-output-format", MERGE_FORMAT,
        "--download-archive", archive_path,
        "--write-subs",
        "--sub-langs", SUB_LANGS,
        "--embed-subs",
        "--ffmpeg-location", FFMPEG_LOCATION,
        "--no-playlist",  # nie traktuj URL jako playlisty
        "--output", os.path.join(output_dir, "%(title)s [%(id)s].%(ext)s"),
        video_url,
    ]

    # Dodaj cookies jeśli podano
    if cookies_file:
        cmd.insert(1, "--cookies")
        cmd.insert(2, cookies_file)
    elif cookies_from_browser:
        cmd.insert(1, "--cookies-from-browser")
        cmd.insert(2, cookies_from_browser)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=1800,  # 30 min max na film
        )

        if result.returncode == 0:
            return True
        else:
            if "has already been recorded in the archive" in result.stdout:
                return True
            print(f"       stderr: {result.stderr[:300]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"       [TIMEOUT] Przekroczono 30 min na pobieranie.")
        return False
    except Exception as e:
        print(f"       [WYJĄTEK] {e}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pobieranie pełnej playlisty YouTube (obsługa >100 filmów)"
    )
    parser.add_argument(
        "url",
        help="URL playlisty YouTube"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Katalog docelowy (domyślnie: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--archive", "-a",
        default=DEFAULT_ARCHIVE_FILE,
        help=f"Plik archiwum pobranych (domyślnie: {DEFAULT_ARCHIVE_FILE})"
    )
    parser.add_argument(
        "--delay", "-d",
        type=int,
        default=DEFAULT_DELAY,
        help=f"Opóźnienie między pobieraniami w sekundach (domyślnie: {DEFAULT_DELAY})"
    )
    parser.add_argument(
        "--cookies", "-c",
        default=None,
        help="Plik cookies (format Netscape, dla niepublicznych playlist)"
    )
    parser.add_argument(
        "--cookies-from-browser",
        default=None,
        help="Pobierz cookies z przeglądarki: chrome, firefox, edge, opera, brave"
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Użyj YouTube Data API v3 (wymaga --api-key)"
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="Klucz YouTube Data API v3"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print(" Pobieranie playlisty YouTube (obsługa >100 filmów)")
    print("=" * 60)
    print()

    archive_path = os.path.abspath(args.archive)
    output_dir = os.path.abspath(args.output_dir)

    # Utwórz katalog docelowy jeśli nie istnieje
    os.makedirs(output_dir, exist_ok=True)

    # Krok 1: Pobierz listę filmów
    if args.use_api and args.api_key:
        entries = get_playlist_entries_api(args.url, args.api_key)
    else:
        entries = get_playlist_entries_ytdlp(args.url, args.cookies, args.cookies_from_browser)

    if not entries:
        print("[BŁĄD] Nie udało się pobrać listy filmów. Sprawdź URL i połączenie.")
        sys.exit(1)

    # Krok 2: Filtruj już pobrane (szybki pre-check)
    to_download = []
    already_done = 0
    for entry in entries:
        if is_already_downloaded(entry["id"], archive_path):
            already_done += 1
        else:
            to_download.append(entry)

    print(f"\n[INFO] Status:")
    print(f"       Wszystkie filmy:   {len(entries)}")
    print(f"       Już pobrane:       {already_done}")
    print(f"       Do pobrania:       {len(to_download)}")
    print()

    if not to_download:
        print("[INFO] Wszystko pobrane. Nic do zrobienia.")
        return

    # Krok 3: Pobieraj jeden po drugim
    success = 0
    failed = []

    try:
        for i, entry in enumerate(to_download, 1):
            title_short = entry["title"][:60]
            print(f"[{i}/{len(to_download)}] {title_short}...")
            print(f"       URL: {entry['url']}")

            ok = download_video(entry["url"], output_dir, archive_path, args.cookies, args.cookies_from_browser)

            if ok:
                success += 1
                print(f"       OK")
            else:
                failed.append(entry)
                print(f"       BŁĄD")

            # Opóźnienie między pobieraniami
            if i < len(to_download):
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print(f"\n\n[INFO] Przerwano przez użytkownika (Ctrl+C).")
        print(f"       Pobrano w tej sesji: {success}")
        print(f"       Uruchom ponownie aby kontynuować.")
        sys.exit(0)

    # Podsumowanie
    print()
    print("=" * 60)
    print(f" PODSUMOWANIE")
    print(f"   Pobrano pomyślnie: {success}")
    print(f"   Błędy:            {len(failed)}")
    print("=" * 60)

    if failed:
        print("\nFilmy z błędami:")
        failed_file = os.path.join(output_dir, "failed_downloads.txt")
        with open(failed_file, "w", encoding="utf-8") as f:
            for entry in failed:
                print(f"  - {entry['title']} ({entry['url']})")
                f.write(f"{entry['url']}\t{entry['title']}\n")
        print(f"\nZapisano listę niepowodzeń do: {failed_file}")
        print("Uruchom skrypt ponownie — automatycznie pominie już pobrane filmy.")


if __name__ == "__main__":
    main()
