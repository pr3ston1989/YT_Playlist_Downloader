"""
Scheduled Downloads — automatyczne sprawdzanie playlist i pobieranie nowych filmów.

Monitoruje podane playlisty i pobiera nowe filmy w określonych odstępach czasu.
Idealny do uruchamiania jako zadanie w tle lub Task Scheduler.

Użycie:
    # Sprawdzaj playlistę co godzinę
    python schedule_download.py "URL" --interval 3600

    # Monitoruj kilka playlist z pliku
    python schedule_download.py --from-file playlisty.txt --interval 7200

    # Jednorazowe sprawdzenie (bez pętli)
    python schedule_download.py "URL" --once

Plik playlisty.txt (jeden URL na linię):
    https://www.youtube.com/playlist?list=PLxxx
    https://www.youtube.com/playlist?list=PLyyy
    # komentarze są ignorowane
"""

import subprocess
import sys
import os
import time
import argparse
from datetime import datetime


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

DEFAULT_INTERVAL = 3600  # 1 godzina
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_SCRIPT = os.path.join(SCRIPT_DIR, "download_playlist.py")


# ============ LOGIKA ============

def load_urls_from_file(filepath: str) -> list[str]:
    """Ładuje URL-e z pliku (jeden na linię, # = komentarz)."""
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def run_download(url: str, extra_args: list[str] = None):
    """Uruchamia download_playlist.py dla jednego URL."""
    cmd = [sys.executable, DOWNLOAD_SCRIPT, url]
    if extra_args:
        cmd.extend(extra_args)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] Sprawdzanie: {url[:60]}...")

    try:
        result = subprocess.run(cmd, timeout=7200)  # max 2h na playlistę
        if result.returncode == 0:
            print(f"[{timestamp}] ✓ Zakończono pomyślnie")
        else:
            print(f"[{timestamp}] ✗ Zakończono z kodem {result.returncode}")
    except subprocess.TimeoutExpired:
        print(f"[{timestamp}] ✗ Timeout (2h)")
    except Exception as e:
        print(f"[{timestamp}] ✗ Błąd: {e}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scheduled Downloads — automatyczne monitorowanie playlist"
    )
    parser.add_argument("url", nargs="?", default=None,
                        help="URL playlisty (opcjonalny jeśli --from-file)")
    parser.add_argument("--from-file", "-f", default=None,
                        help="Plik z listą URL (jeden na linię)")
    parser.add_argument("--interval", "-i", type=int, default=DEFAULT_INTERVAL,
                        help=f"Interwał sprawdzania w sekundach (domyślnie: {DEFAULT_INTERVAL})")
    parser.add_argument("--once", action="store_true",
                        help="Jednorazowe sprawdzenie (bez pętli)")
    parser.add_argument("--audio-only", action="store_true",
                        help="Przekaż --audio-only do download_playlist.py")
    parser.add_argument("--parallel", "-p", type=int, default=None,
                        help="Przekaż --parallel N")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Przekaż --output-dir")
    return parser.parse_args()


def main():
    args = parse_args()

    # Zbierz URL-e
    urls = []
    if args.url:
        urls.append(args.url)
    if args.from_file:
        if not os.path.exists(args.from_file):
            print(f"[BŁĄD] Plik nie istnieje: {args.from_file}")
            sys.exit(1)
        urls.extend(load_urls_from_file(args.from_file))

    if not urls:
        print("[BŁĄD] Podaj URL lub --from-file")
        sys.exit(1)

    # Zbuduj dodatkowe argumenty
    extra_args = ["--no-beep"]
    if args.audio_only:
        extra_args.append("--audio-only")
    if args.parallel:
        extra_args.extend(["--parallel", str(args.parallel)])
    if args.output_dir:
        extra_args.extend(["--output-dir", args.output_dir])

    print("=" * 60)
    print(" Scheduled Downloads")
    print(f" Playlist: {len(urls)}")
    print(f" Interwał: {args.interval}s ({args.interval // 60} min)")
    if args.once:
        print(" Tryb: jednorazowy")
    print("=" * 60)

    iteration = 0
    try:
        while True:
            iteration += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{'─' * 60}")
            print(f" Iteracja #{iteration} — {timestamp}")
            print(f"{'─' * 60}")

            for url in urls:
                run_download(url, extra_args)

            if args.once:
                break

            next_run = datetime.now().strftime("%H:%M:%S")
            print(f"\n[CZEKAM] Następne sprawdzenie za {args.interval}s...")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n[STOP] Zatrzymano po {iteration} iteracjach.")


if __name__ == "__main__":
    main()
