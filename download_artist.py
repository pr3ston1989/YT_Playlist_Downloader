"""
Skrypt do wyszukiwania i pobierania utworów artysty z YouTube.

Dwa tryby wyszukiwania:
1. yt-dlp ytsearch (domyślny) — wyszukuje na YouTube "artysta" i pobiera N wyników
2. ytmusicapi (opcjonalny) — przeszukuje YouTube Music, zwraca oficjalne utwory artysty

Użycie:
    python download_artist.py "Nazwa Artysty"
    python download_artist.py "Metallica" --max-results 50
    python download_artist.py "Rammstein" --use-ytmusic

Wymaga:
    - yt-dlp.exe w aktualnym katalogu lub PATH
    - ffmpeg.exe w aktualnym katalogu
    - (opcjonalnie) pip install ytmusicapi  — dla trybu --use-ytmusic
"""

import subprocess
import json
import sys
import os
import time
import argparse

# ============ DOMYŚLNE USTAWIENIA ============

DEFAULT_OUTPUT_DIR = "."
DEFAULT_ARCHIVE_FILE = "pobrane.txt"
FFMPEG_LOCATION = "."

# Opcje pobierania
FORMAT = "bestvideo+bestaudio/best"
MERGE_FORMAT = "mkv"
SUB_LANGS = "pl,en"

DEFAULT_MAX_RESULTS = 30
DEFAULT_DELAY = 2

# ============ KONIEC USTAWIEŃ ============


def search_ytdlp(artist: str, max_results: int) -> list[dict]:
    """
    Wyszukuje teledyski artysty przez yt-dlp ytsearch.
    Pobiera więcej wyników niż potrzeba, potem filtruje po słowach kluczowych
    wskazujących na oficjalny teledysk.
    """
    # Szukamy więcej wyników żeby po filtracji mieć wystarczająco
    search_count = max_results * 3
    query = f"{artist} official music video"
    search_term = f"ytsearch{search_count}:{query}"

    print(f"[INFO] Wyszukiwanie teledysków: '{artist}' (szukam {search_count}, filtruję do {max_results})...")

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        search_term,
    ]

    raw_entries = []

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

        if result.returncode != 0:
            print(f"[BŁĄD] yt-dlp search zakończył się kodem {result.returncode}")
            print(f"       stderr: {result.stderr[:500]}")
            return []

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                video_id = entry.get("id", "")
                title = entry.get("title", "Bez tytułu")
                channel = entry.get("channel", "") or entry.get("uploader", "") or ""
                url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"

                if not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={url}"

                raw_entries.append({
                    "id": video_id,
                    "title": title,
                    "channel": channel,
                    "url": url,
                })
            except json.JSONDecodeError:
                continue

    except subprocess.TimeoutExpired:
        print("[BŁĄD] Timeout przy wyszukiwaniu (120s)")
        return []
    except FileNotFoundError:
        print("[BŁĄD] yt-dlp nie znaleziony.")
        return []

    # Filtruj — zostaw tylko prawdopodobne teledyski
    entries = filter_music_videos(raw_entries, artist, max_results)
    print(f"[INFO] Znaleziono {len(entries)} teledysków (z {len(raw_entries)} wyników).")
    return entries


def filter_music_videos(entries: list[dict], artist: str, max_results: int) -> list[dict]:
    """
    Filtruje wyniki, zostawiając tylko te które wyglądają na oficjalne teledyski.
    Priorytet:
      1. Tytuł zawiera "official" + ("video" lub "music video")
      2. Tytuł zawiera "official"
      3. Kanał zawiera nazwę artysty (oficjalny kanał)
    Odrzuca: live, cover, reaction, lyrics, karaoke, remix (chyba że oficjalny)
    """
    artist_lower = artist.lower()

    # Słowa wykluczające (nie-teledyski)
    exclude_keywords = ["live", "concert", "cover", "reaction", "karaoke", "tutorial",
                        "drum cam", "guitar lesson", "bass cover", "piano cover",
                        "interview", "behind the scenes", "making of", "unboxing"]

    # Słowa wskazujące na teledysk
    video_keywords = ["official music video", "official video", "official mv",
                      "music video", "oficjalny teledysk", "teledysk", "videoclip"]

    scored = []

    for entry in entries:
        title_lower = entry["title"].lower()
        channel_lower = entry.get("channel", "").lower()

        # Odrzuć oczywiste nie-teledyski
        if any(kw in title_lower for kw in exclude_keywords):
            # Ale nie odrzucaj jeśli ma "official video" w tytule
            if not any(vk in title_lower for vk in video_keywords):
                continue

        # Odrzuć jeśli w tytule nie ma nawet częściowego dopasowania do artysty
        # (pierwsze słowo artysty wystarczy)
        artist_first_word = artist_lower.split()[0]
        if artist_first_word not in title_lower and artist_first_word not in channel_lower:
            continue

        # Scoring
        score = 0

        # Oficjalny teledysk w tytule = najwyższy priorytet
        if any(vk in title_lower for vk in video_keywords):
            score += 10

        # "official" w tytule
        if "official" in title_lower or "oficjaln" in title_lower:
            score += 5

        # Kanał pasuje do artysty
        if artist_lower in channel_lower or artist_first_word in channel_lower:
            score += 3

        # Pełna nazwa artysty w tytule
        if artist_lower in title_lower:
            score += 2

        # Lyrics/audio only — niższy priorytet (ale nie wykluczaj)
        if "lyrics" in title_lower or "lyric video" in title_lower:
            score -= 3
        if "audio" in title_lower and "video" not in title_lower:
            score -= 4

        scored.append((score, entry))

    # Sortuj po score malejąco
    scored.sort(key=lambda x: x[0], reverse=True)

    # Zwróć top wyniki
    return [entry for _, entry in scored[:max_results]]


def search_ytmusic(artist: str, max_results: int) -> list[dict]:
    """
    Wyszukuje teledyski artysty przez YouTube Music API (ytmusicapi).
    Szuka w kategorii "videos" — zwraca oficjalne teledyski.

    Wymaga: pip install ytmusicapi
    """
    try:
        from ytmusicapi import YTMusic
    except ImportError:
        print("[BŁĄD] Brak modułu ytmusicapi. Zainstaluj: pip install ytmusicapi")
        print("       Lub użyj trybu domyślnego (bez --use-ytmusic)")
        return []

    print(f"[INFO] Wyszukiwanie teledysków '{artist}' w YouTube Music...")
    ytm = YTMusic()

    entries = []

    # Szukaj artysty
    search_results = ytm.search(artist, filter="artists")
    if not search_results:
        print(f"[BŁĄD] Nie znaleziono artysty '{artist}' w YouTube Music.")
        return []

    artist_data = search_results[0]
    artist_id = artist_data.get("browseId")
    artist_name = artist_data.get("artist", artist)
    print(f"[INFO] Znaleziono artystę: {artist_name}")

    if artist_id:
        try:
            artist_page = ytm.get_artist(artist_id)

            # Szukaj sekcji "videos" (teledyski) — to jest to czego chcemy
            videos_section = artist_page.get("videos", {})
            videos_browse_id = videos_section.get("browseId")

            if videos_browse_id:
                # Pobierz pełną listę teledysków
                all_videos = ytm.get_playlist(videos_browse_id, limit=max_results)
                tracks = all_videos.get("tracks", [])
            else:
                # Użyj tych co są na stronie artysty
                tracks = videos_section.get("results", [])

            for track in tracks[:max_results]:
                video_id = track.get("videoId", "")
                if not video_id:
                    continue
                title = track.get("title", "Bez tytułu")
                entries.append({
                    "id": video_id,
                    "title": f"{artist_name} - {title}",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                })

        except Exception as e:
            print(f"[UWAGA] Nie udało się pobrać strony artysty: {e}")

    # Fallback: szukaj teledysków bezpośrednio
    if not entries:
        print("[INFO] Fallback: wyszukiwanie teledysków po nazwie...")
        video_results = ytm.search(artist, filter="videos", limit=max_results)
        for track in video_results[:max_results]:
            video_id = track.get("videoId", "")
            if not video_id:
                continue
            title = track.get("title", "Bez tytułu")
            track_artist = ", ".join(a["name"] for a in track.get("artists", []))
            entries.append({
                "id": video_id,
                "title": f"{track_artist} - {title}" if track_artist else title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

    print(f"[INFO] Znaleziono {len(entries)} teledysków.")
    return entries


def is_already_downloaded(video_id: str, archive_path: str) -> bool:
    """Sprawdza, czy film jest już w pliku archiwum."""
    if not os.path.exists(archive_path):
        return False
    with open(archive_path, "r", encoding="utf-8") as f:
        for line in f:
            if video_id in line:
                return True
    return False


def download_video(video_url: str, output_dir: str, archive_path: str) -> bool:
    """Pobiera pojedynczy film za pomocą yt-dlp."""
    cmd = [
        "yt-dlp",
        "-f", FORMAT,
        "--merge-output-format", MERGE_FORMAT,
        "--download-archive", archive_path,
        "--write-subs",
        "--sub-langs", SUB_LANGS,
        "--embed-subs",
        "--ffmpeg-location", FFMPEG_LOCATION,
        "--no-playlist",
        "--output", os.path.join(output_dir, "%(title)s [%(id)s].%(ext)s"),
        video_url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=1800,
        )

        if result.returncode == 0:
            return True
        else:
            if "has already been recorded in the archive" in result.stdout:
                return True
            print(f"       stderr: {result.stderr[:300]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"       [TIMEOUT] Przekroczono 30 min.")
        return False
    except Exception as e:
        print(f"       [WYJĄTEK] {e}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Wyszukiwanie i pobieranie utworów artysty z YouTube"
    )
    parser.add_argument(
        "artist",
        help="Nazwa artysty/zespołu do wyszukania"
    )
    parser.add_argument(
        "--max-results", "-n",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=f"Maksymalna liczba wyników wyszukiwania (domyślnie: {DEFAULT_MAX_RESULTS})"
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
        help=f"Opóźnienie między pobieraniami (domyślnie: {DEFAULT_DELAY}s)"
    )
    parser.add_argument(
        "--use-ytmusic",
        action="store_true",
        help="Użyj YouTube Music API (lepsza dyskografia, wymaga: pip install ytmusicapi)"
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Tylko wyświetl znalezione utwory, nie pobieraj"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print(f" Pobieranie utworów: {args.artist}")
    print("=" * 60)
    print()

    archive_path = os.path.abspath(args.archive)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Krok 1: Wyszukaj utwory
    if args.use_ytmusic:
        entries = search_ytmusic(args.artist, args.max_results)
    else:
        entries = search_ytdlp(args.artist, args.max_results)

    if not entries:
        print("[BŁĄD] Nie znaleziono utworów.")
        sys.exit(1)

    # Tryb list-only: wyświetl i zakończ
    if args.list_only:
        print(f"\nZnalezione utwory ({len(entries)}):")
        for i, entry in enumerate(entries, 1):
            status = "[POBRANE]" if is_already_downloaded(entry["id"], archive_path) else "[NOWE]"
            print(f"  {i:3}. {status} {entry['title']}")
            print(f"       {entry['url']}")
        return

    # Krok 2: Filtruj już pobrane
    to_download = []
    already_done = 0
    for entry in entries:
        if is_already_downloaded(entry["id"], archive_path):
            already_done += 1
        else:
            to_download.append(entry)

    print(f"\n[INFO] Status:")
    print(f"       Znalezione:       {len(entries)}")
    print(f"       Już pobrane:      {already_done}")
    print(f"       Do pobrania:      {len(to_download)}")
    print()

    if not to_download:
        print("[INFO] Wszystkie znalezione utwory są już pobrane.")
        return

    # Krok 3: Pobieraj
    success = 0
    failed = []

    try:
        for i, entry in enumerate(to_download, 1):
            title_short = entry["title"][:60]
            print(f"[{i}/{len(to_download)}] {title_short}...")

            ok = download_video(entry["url"], output_dir, archive_path)

            if ok:
                success += 1
                print(f"       OK")
            else:
                failed.append(entry)
                print(f"       BŁĄD")

            if i < len(to_download):
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print(f"\n\n[INFO] Przerwano (Ctrl+C). Pobrano w tej sesji: {success}")
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
        print("\nUtwory z błędami:")
        for entry in failed:
            print(f"  - {entry['title']}")


if __name__ == "__main__":
    main()
