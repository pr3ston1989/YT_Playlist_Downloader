"""
Skrypt do pobierania pełnej playlisty YouTube (>100 filmów).

Funkcje:
- Obejście limitu 100 pozycji (paginacja + YouTube Data API fallback)
- Pasek postępu pobierania w czasie rzeczywistym
- Równoległe pobieranie (--parallel N)
- Automatyczne retry z backoff przy błędach
- Tryb audio-only (--audio-only)
- Filtrowanie po długości (--min-duration, --max-duration)
- Eksport listy URL (--export-urls)
- Kolorowy output
- Logowanie do pliku (--log)
- Szacowany czas pozostały (ETA)
- Powiadomienie dźwiękowe po zakończeniu

Użycie:
    python download_playlist.py "URL"
    python download_playlist.py "URL" --parallel 3 --audio-only
    python download_playlist.py "URL" --min-duration 60 --max-duration 600
    python download_playlist.py "URL" --export-urls lista.txt
    python download_playlist.py "URL" --log pobieranie.log
"""

import subprocess
import json
import sys
import os
import time
import argparse
import threading
import logging
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

# ============ KOLORY (Windows compatible) ============

def _init_colors():
    """Włącza obsługę kolorów ANSI w Windows CMD."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

_init_colors()

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def color_ok(text):
    return f"{Colors.GREEN}{text}{Colors.RESET}"

def color_err(text):
    return f"{Colors.RED}{text}{Colors.RESET}"

def color_warn(text):
    return f"{Colors.YELLOW}{text}{Colors.RESET}"

def color_info(text):
    return f"{Colors.CYAN}{text}{Colors.RESET}"

def color_bold(text):
    return f"{Colors.BOLD}{text}{Colors.RESET}"


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


# ============ DOMYŚLNE USTAWIENIA ============

DEFAULT_OUTPUT_DIR = "."
DEFAULT_ARCHIVE_FILE = "pobrane.txt"
FFMPEG_LOCATION = "."

FORMAT_VIDEO = "bestvideo+bestaudio/best"
FORMAT_AUDIO = "bestaudio/best"
MERGE_FORMAT = "mkv"
AUDIO_FORMAT = "mp3"
SUB_LANGS = "pl,en"

DEFAULT_DELAY = 2
DEFAULT_RETRIES = 3
DEFAULT_PARALLEL = 1

DEFAULT_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# ============ KONIEC USTAWIEŃ ============


# ============ LOGGER ============

logger = logging.getLogger("yt_downloader")
logger.setLevel(logging.DEBUG)

# Console handler (INFO+)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_console_handler)


def setup_file_logger(log_path: str):
    """Dodaje logowanie do pliku."""
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)


# ============ FUNKCJE POMOCNICZE ============

def format_duration(seconds: float) -> str:
    """Formatuje sekundy do czytelnej formy."""
    if seconds < 0:
        return "??:??"
    td = timedelta(seconds=int(seconds))
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if td.days > 0 or hours > 0:
        return f"{td.days * 24 + hours}h {minutes:02d}m"
    return f"{minutes:02d}:{secs:02d}"


def beep():
    """Powiadomienie dźwiękowe."""
    try:
        if sys.platform == "win32":
            import winsound
            winsound.Beep(800, 300)
            time.sleep(0.1)
            winsound.Beep(1000, 300)
        else:
            print("\a")
    except Exception:
        print("\a")


# ============ POBIERANIE LISTY PLAYLISTY ============

def get_playlist_entries_ytdlp(playlist_url: str, cookies_file: str = None,
                                cookies_from_browser: str = None) -> list[dict]:
    """Pobiera listę filmów z playlisty (z obsługą paginacji)."""
    logger.info(f"{color_info('[INFO]')} Pobieranie listy filmów z playlisty...")
    logger.info(f"       URL: {playlist_url}")

    entries = _fetch_flat_playlist(playlist_url, cookies_file, cookies_from_browser)

    if len(entries) == 100:
        logger.info(f"{color_warn('[INFO]')} Wykryto limit 100. Pobieranie w partiach...")
        entries = _fetch_playlist_in_batches(playlist_url, cookies_file, cookies_from_browser)

    logger.info(f"{color_info('[INFO]')} Znaleziono {color_bold(str(len(entries)))} filmów.")
    return entries


def _fetch_flat_playlist(playlist_url: str, cookies_file: str = None,
                         cookies_from_browser: str = None,
                         start: int = None, end: int = None) -> list[dict]:
    cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "--no-warnings"]

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
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=300)
        if result.returncode != 0:
            if start and "is not in the playlist" not in (result.stderr or ""):
                logger.debug(f"flat-playlist error: {result.stderr[:300]}")
            return []

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                video_id = entry.get("id", "")
                title = entry.get("title", "Bez tytułu")
                duration = entry.get("duration")  # sekundy lub None
                url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
                if not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={url}"
                entries.append({"id": video_id, "title": title, "url": url, "duration": duration})
            except json.JSONDecodeError:
                continue
    except subprocess.TimeoutExpired:
        logger.error(f"{color_err('[BŁĄD]')} Timeout (300s)")
    except FileNotFoundError:
        logger.error(f"{color_err('[BŁĄD]')} yt-dlp nie znaleziony!")

    return entries


def _fetch_playlist_in_batches(playlist_url: str, cookies_file=None, cookies_from_browser=None) -> list[dict]:
    all_entries = []
    seen_ids = set()
    batch_size = 50
    start = 1

    while True:
        end = start + batch_size - 1
        print(f"       Partia {start}-{end}...", end=" ", flush=True)
        batch = _fetch_flat_playlist(playlist_url, cookies_file, cookies_from_browser, start=start, end=end)

        new_entries = [e for e in batch if e["id"] not in seen_ids]
        seen_ids.update(e["id"] for e in new_entries)
        all_entries.extend(new_entries)
        print(f"({len(new_entries)} nowych)")

        if len(batch) < batch_size:
            break
        start += batch_size
        if start > 2000:
            logger.warning(f"{color_warn('[UWAGA]')} Przekroczono 2000 pozycji.")
            break

    return all_entries


def get_playlist_entries_api(playlist_url: str, api_key: str) -> list[dict]:
    """Pobiera listę przez YouTube Data API v3."""
    import requests
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(playlist_url)
    params = parse_qs(parsed.query)
    playlist_id = params.get("list", [None])[0]
    if not playlist_id:
        logger.error(f"{color_err('[BŁĄD]')} Nie można wyciągnąć ID playlisty.")
        return []

    logger.info(f"{color_info('[INFO]')} YouTube Data API — Playlist: {playlist_id}")
    entries = []
    page_token = None

    while True:
        req_params = {"part": "snippet,contentDetails", "playlistId": playlist_id,
                      "maxResults": 50, "key": api_key}
        if page_token:
            req_params["pageToken"] = page_token

        resp = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params=req_params)
        if resp.status_code != 200:
            logger.error(f"{color_err('[BŁĄD]')} API status {resp.status_code}")
            break

        data = resp.json()
        for item in data.get("items", []):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            title = snippet.get("title", "Bez tytułu")
            if title in ("Deleted video", "Private video"):
                continue
            entries.append({"id": video_id, "title": title,
                           "url": f"https://www.youtube.com/watch?v={video_id}", "duration": None})

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    logger.info(f"{color_info('[INFO]')} API zwróciło {len(entries)} filmów.")
    return entries


# ============ ARCHIWUM ============

def load_archive(archive_path: str) -> set:
    """Ładuje zbiór ID z archiwum (szybsze niż sprawdzanie per-film)."""
    if not os.path.exists(archive_path):
        return set()
    ids = set()
    with open(archive_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                ids.add(parts[1])
            elif parts:
                ids.add(parts[0])
    return ids


# ============ POBIERANIE FILMÓW ============

def _cleanup_subtitle_files(output_dir: str):
    """Usuwa pliki .vtt i .srt pozostawione po osadzeniu napisów."""
    for pattern in ("*.vtt", "*.srt", "*.ass"):
        for f in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(f)
            except OSError:
                pass


def download_video(video_url: str, output_dir: str, archive_path: str,
                   cookies_file=None, cookies_from_browser=None,
                   audio_only=False, thumbnail=False, retries=3) -> tuple[bool, str]:
    """
    Pobiera film z retry. Zwraca (sukces, komunikat).
    Wyświetla progress w czasie rzeczywistym.
    """
    fmt = FORMAT_AUDIO if audio_only else FORMAT_VIDEO

    cmd = ["yt-dlp", "-f", fmt, "--download-archive", archive_path,
           "--write-subs", "--sub-langs", SUB_LANGS, "--embed-subs",
           "--ffmpeg-location", FFMPEG_LOCATION, "--no-playlist",
           "--newline",
           "--output", os.path.join(output_dir, "%(title)s [%(id)s].%(ext)s"),
           video_url]

    if not audio_only:
        cmd.extend(["--merge-output-format", MERGE_FORMAT])
    else:
        cmd.extend(["--extract-audio", "--audio-format", AUDIO_FORMAT])

    # Thumbnail jako okładka
    if thumbnail:
        cmd.extend(["--embed-thumbnail", "--write-thumbnail"])

    if cookies_file:
        cmd[1:1] = ["--cookies", cookies_file]
    elif cookies_from_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_from_browser]

    for attempt in range(1, retries + 1):
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace"
            )

            last_progress = ""
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                line = line.strip()
                # Parsuj progress z yt-dlp
                if line.startswith("[download]") and "%" in line:
                    # Wyświetl progress w tej samej linii
                    pct = line.split("%")[0].split()[-1]
                    speed = ""
                    eta = ""
                    if "at" in line:
                        parts = line.split("at")
                        if len(parts) > 1:
                            speed = parts[1].split("ETA")[0].strip()
                    if "ETA" in line:
                        eta = line.split("ETA")[-1].strip()
                    last_progress = f"       {Colors.DIM}{pct}% | {speed} | ETA: {eta}{Colors.RESET}"
                    print(f"\r{last_progress}", end="", flush=True)

            process.wait(timeout=1800)
            stderr_output = process.stderr.read()

            if last_progress:
                print()  # nowa linia po progress

            if process.returncode == 0:
                _cleanup_subtitle_files(output_dir)
                return True, "OK"
            elif "has already been recorded" in (stderr_output or ""):
                return True, "już pobrane"
            else:
                error_msg = stderr_output[:200] if stderr_output else "nieznany błąd"
                if attempt < retries:
                    wait = attempt * 5
                    logger.debug(f"Retry {attempt}/{retries}, czekam {wait}s...")
                    print(f"       {color_warn(f'Retry {attempt}/{retries} za {wait}s...')}")
                    time.sleep(wait)
                else:
                    return False, error_msg

        except subprocess.TimeoutExpired:
            process.kill()
            if attempt < retries:
                print(f"       {color_warn(f'Timeout, retry {attempt}/{retries}...')}")
                time.sleep(attempt * 5)
            else:
                return False, "timeout"
        except Exception as e:
            return False, str(e)

    return False, "wyczerpano próby"


# ============ EKSPORT ============

def export_urls(entries: list[dict], filepath: str):
    """Eksportuje listę URL do pliku."""
    with open(filepath, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(f"{entry['url']}\t{entry['title']}\n")
    logger.info(f"{color_ok('[OK]')} Wyeksportowano {len(entries)} URL do: {filepath}")


# ============ FILTROWANIE ============

def filter_by_duration(entries: list[dict], min_dur: int = None, max_dur: int = None) -> list[dict]:
    """Filtruje wpisy po długości (sekundy)."""
    if min_dur is None and max_dur is None:
        return entries

    filtered = []
    skipped = 0
    for entry in entries:
        dur = entry.get("duration")
        if dur is None:
            filtered.append(entry)  # brak info o długości — przepuść
            continue
        if min_dur and dur < min_dur:
            skipped += 1
            continue
        if max_dur and dur > max_dur:
            skipped += 1
            continue
        filtered.append(entry)

    if skipped:
        logger.info(f"{color_warn('[FILTR]')} Pominięto {skipped} filmów (czas trwania poza zakresem)")
    return filtered


# ============ ARGPARSE ============

def parse_args():
    parser = argparse.ArgumentParser(
        description="Pobieranie playlisty YouTube (>100 filmów, z postępem i retry)"
    )
    parser.add_argument("url", nargs="?", default=None,
                        help="URL playlisty/kanału YouTube (opcjonalny z --from-file)")
    parser.add_argument("--from-file", default=None,
                        help="Plik z listą URL (jeden na linię, # = komentarz)")
    parser.add_argument("--channel", action="store_true",
                        help="Traktuj URL jako kanał (pobierz wszystkie filmy)")
    parser.add_argument("--output-dir", "-o", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archive", "-a", default=DEFAULT_ARCHIVE_FILE)
    parser.add_argument("--delay", "-d", type=int, default=DEFAULT_DELAY,
                        help=f"Opóźnienie między pobieraniami (domyślnie: {DEFAULT_DELAY}s)")
    parser.add_argument("--parallel", "-p", type=int, default=DEFAULT_PARALLEL,
                        help=f"Liczba równoległych pobierań (domyślnie: {DEFAULT_PARALLEL})")
    parser.add_argument("--retries", "-r", type=int, default=DEFAULT_RETRIES,
                        help=f"Liczba prób przy błędzie (domyślnie: {DEFAULT_RETRIES})")
    parser.add_argument("--cookies", "-c", default=None)
    parser.add_argument("--cookies-from-browser", default=None)
    parser.add_argument("--use-api", action="store_true")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--audio-only", action="store_true",
                        help="Pobieraj tylko audio (MP3)")
    parser.add_argument("--thumbnail", action="store_true",
                        help="Pobierz miniaturkę i osadź jako okładkę")
    parser.add_argument("--min-duration", type=int, default=None,
                        help="Min. długość filmu w sekundach")
    parser.add_argument("--max-duration", type=int, default=None,
                        help="Max. długość filmu w sekundach")
    parser.add_argument("--export-urls", default=None,
                        help="Eksportuj listę URL do pliku (bez pobierania)")
    parser.add_argument("--interactive", action="store_true",
                        help="Tryb interaktywny — wybierz które filmy pobrać")
    parser.add_argument("--log", default=None,
                        help="Zapisz log do pliku")
    parser.add_argument("--no-beep", action="store_true",
                        help="Wyłącz powiadomienie dźwiękowe")
    return parser.parse_args()


# ============ INTERAKTYWNY SELEKTOR ============

def interactive_select(entries: list[dict]) -> list[dict]:
    """Wyświetla listę filmów i pozwala użytkownikowi wybrać które pobrać."""
    print(f"\n{color_bold('TRYB INTERAKTYWNY')} — wybierz filmy do pobrania")
    print(f"Wpisz numery (np: 1,3,5-10) lub 'all' dla wszystkich, 'q' aby wyjść\n")

    for i, entry in enumerate(entries, 1):
        dur = entry.get("duration")
        dur_str = f" [{dur // 60}:{dur % 60:02d}]" if dur else ""
        print(f"  {i:3}. {entry['title'][:60]}{dur_str}")

    print()
    while True:
        choice = input(f"Wybór ({len(entries)} dostępnych): ").strip().lower()

        if choice == "q":
            sys.exit(0)
        if choice == "all":
            return entries

        # Parsuj numery: 1,3,5-10
        selected_indices = set()
        try:
            for part in choice.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-", 1)
                    for n in range(int(start), int(end) + 1):
                        selected_indices.add(n)
                else:
                    selected_indices.add(int(part))
        except ValueError:
            print("  Nieprawidłowy format. Użyj: 1,3,5-10")
            continue

        selected = [entries[i - 1] for i in sorted(selected_indices) if 1 <= i <= len(entries)]
        if selected:
            print(f"\n  Wybrano {len(selected)} filmów.")
            return selected
        print("  Nic nie wybrano, spróbuj ponownie.")


# ============ FROM-FILE ============

def load_urls_from_file(filepath: str) -> list[str]:
    """Ładuje URL-e z pliku (jeden na linię, # = komentarz)."""
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                # Może być format: URL\tTytuł (z eksportu)
                url = line.split("\t")[0].strip()
                if url.startswith("http"):
                    urls.append(url)
    return urls


# ============ MAIN ============

def main():
    args = parse_args()

    # Walidacja — potrzebujemy URL lub --from-file
    if not args.url and not args.from_file:
        print(f"{color_err('[BŁĄD]')} Podaj URL lub --from-file")
        sys.exit(1)

    # Logowanie do pliku
    if args.log:
        setup_file_logger(args.log)

    print(f"\n{color_bold('=' * 60)}")
    print(f"{color_bold(' YT Playlist Downloader')}")
    if args.audio_only:
        print(f" Tryb: {color_warn('AUDIO ONLY (MP3)')}")
    if args.thumbnail:
        print(f" Thumbnail: {color_info('tak (osadzana okładka)')}")
    if args.parallel > 1:
        print(f" Równoległe: {color_info(str(args.parallel))} wątków")
    if args.channel:
        print(f" Tryb: {color_info('KANAŁ (wszystkie filmy)')}")
    if args.from_file:
        print(f" Źródło: {color_info(args.from_file)}")
    print(f"{color_bold('=' * 60)}\n")

    archive_path = os.path.abspath(args.archive)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # === TRYB FROM-FILE: pobierz każdy URL osobno ===
    if args.from_file:
        urls = load_urls_from_file(args.from_file)
        if args.url:
            urls.insert(0, args.url)
        if not urls:
            print(f"{color_err('[BŁĄD]')} Plik nie zawiera URL.")
            sys.exit(1)

        print(f"{color_info('[INFO]')} Załadowano {len(urls)} URL z pliku.\n")

        # Każdy URL traktujemy jako osobny film do pobrania
        success = 0
        failed_urls = []
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url[:60]}...")
            ok, msg = download_video(url, output_dir, archive_path,
                                     args.cookies, args.cookies_from_browser,
                                     audio_only=args.audio_only,
                                     thumbnail=args.thumbnail,
                                     retries=args.retries)
            if ok:
                success += 1
                print(f"       {color_ok('✓ ' + msg)}")
            else:
                failed_urls.append(url)
                print(f"       {color_err('✗ ' + msg[:60])}")
            if i < len(urls):
                time.sleep(args.delay)

        print(f"\n{color_bold('PODSUMOWANIE:')} Pobrano {success}/{len(urls)}")
        if not args.no_beep:
            beep()
        return

    # === TRYB KANAŁ: URL kanału ===
    url = args.url
    if args.channel:
        # Upewnij się że URL wskazuje na /videos
        if "/videos" not in url and "@" in url:
            url = url.rstrip("/") + "/videos"

    # Krok 1: Pobierz listę
    api_key = args.api_key or DEFAULT_API_KEY
    if args.use_api and api_key:
        entries = get_playlist_entries_api(url, api_key)
    else:
        entries = get_playlist_entries_ytdlp(url, args.cookies, args.cookies_from_browser)
        if len(entries) <= 100 and api_key:
            logger.info(f"{color_info('[INFO]')} Próbuję YouTube Data API...")
            api_entries = get_playlist_entries_api(url, api_key)
            if len(api_entries) > len(entries):
                entries = api_entries

    if not entries:
        logger.error(f"{color_err('[BŁĄD]')} Nie znaleziono filmów.")
        sys.exit(1)

    # Filtrowanie po długości
    entries = filter_by_duration(entries, args.min_duration, args.max_duration)

    # Eksport URL
    if args.export_urls:
        export_urls(entries, args.export_urls)
        return

    # Krok 2: Filtruj już pobrane
    archive_ids = load_archive(archive_path)
    to_download = [e for e in entries if e["id"] not in archive_ids]
    already_done = len(entries) - len(to_download)

    print(f"\n{color_info('[INFO]')} Status:")
    print(f"       Wszystkie:     {color_bold(str(len(entries)))}")
    print(f"       Już pobrane:   {color_ok(str(already_done))}")
    print(f"       Do pobrania:   {color_warn(str(len(to_download)))}")
    print()

    if not to_download:
        print(f"{color_ok('[INFO]')} Wszystko pobrane!")
        return

    # Tryb interaktywny — pozwól wybrać
    if args.interactive:
        to_download = interactive_select(to_download)
        if not to_download:
            return

    # Krok 3: Pobieraj
    success = 0
    failed = []
    start_time = time.time()
    lock = threading.Lock()

    def _download_one(i_entry):
        nonlocal success
        i, entry = i_entry
        title_short = entry["title"][:55]

        with lock:
            elapsed = time.time() - start_time
            if success > 0:
                avg_time = elapsed / success
                remaining = avg_time * (len(to_download) - i)
                eta_str = format_duration(remaining)
            else:
                eta_str = "obliczam..."
            print(f"\n{color_bold(f'[{i}/{len(to_download)}]')} {title_short}...")
            print(f"       ETA pozostałe: ~{eta_str}")
            logger.debug(f"Pobieranie: {entry['url']}")

        ok, msg = download_video(
            entry["url"], output_dir, archive_path,
            args.cookies, args.cookies_from_browser,
            audio_only=args.audio_only, thumbnail=args.thumbnail,
            retries=args.retries
        )

        with lock:
            if ok:
                success += 1
                print(f"       {color_ok('✓ ' + msg)}")
            else:
                failed.append(entry)
                print(f"       {color_err('✗ ' + msg[:80])}")

        return ok

    try:
        if args.parallel > 1:
            # Pobieranie równoległe
            with ThreadPoolExecutor(max_workers=args.parallel) as executor:
                futures = {executor.submit(_download_one, (i, e)): e
                           for i, e in enumerate(to_download, 1)}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.debug(f"Thread error: {e}")
        else:
            # Pobieranie sekwencyjne
            for i, entry in enumerate(to_download, 1):
                _download_one((i, entry))
                if i < len(to_download):
                    time.sleep(args.delay)

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n{color_warn('[PRZERWANO]')} Ctrl+C")
        print(f"       Pobrano: {success} | Czas: {format_duration(elapsed)}")
        print(f"       Uruchom ponownie aby kontynuować.")
        sys.exit(0)

    # Podsumowanie
    elapsed = time.time() - start_time
    print(f"\n{color_bold('=' * 60)}")
    print(f" {color_bold('PODSUMOWANIE')}")
    print(f"   Pobrano:   {color_ok(str(success))}")
    print(f"   Błędy:     {color_err(str(len(failed)))}")
    print(f"   Czas:      {format_duration(elapsed)}")
    print(f"{color_bold('=' * 60)}")

    if failed:
        print(f"\n{color_err('Filmy z błędami:')}")
        failed_file = os.path.join(output_dir, "failed_downloads.txt")
        with open(failed_file, "w", encoding="utf-8") as f:
            for entry in failed:
                print(f"  - {entry['title']}")
                f.write(f"{entry['url']}\t{entry['title']}\n")
        print(f"\nZapisano do: {failed_file}")

    # Powiadomienie dźwiękowe
    if not args.no_beep:
        beep()


if __name__ == "__main__":
    main()
