"""
Statystyki pobieranych plików.

Wyświetla informacje o pobranych filmach: ile GB, ile plików,
top artystów, formaty, historia.

Użycie:
    python stats.py
    python stats.py --dir "D:\\Muzyka"
    python stats.py --detailed
"""

import os
import re
import argparse
from collections import Counter
from datetime import datetime


# ============ USTAWIENIA ============

DEFAULT_DIR = "."
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".opus", ".m4a", ".ogg", ".wav", ".flac"}
ALL_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


# ============ ANALIZA ============

def scan_files(directory: str) -> list[dict]:
    """Skanuje katalog i zbiera info o pobranych plikach."""
    files = []
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath):
            continue

        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALL_EXTENSIONS:
            continue

        size = os.path.getsize(filepath)
        mtime = os.path.getmtime(filepath)

        # Próbuj wyciągnąć artystę z nazwy (format: "Artysta - Tytuł [ID].ext")
        artist = extract_artist(filename)

        files.append({
            "filename": filename,
            "filepath": filepath,
            "size": size,
            "ext": ext,
            "mtime": mtime,
            "artist": artist,
            "is_video": ext in VIDEO_EXTENSIONS,
            "is_audio": ext in AUDIO_EXTENSIONS,
        })

    return files


def extract_artist(filename: str) -> str:
    """Próbuje wyciągnąć artystę z nazwy pliku."""
    # Wzorzec: "Artysta - Tytuł [ID].ext"
    match = re.match(r"^(.+?)\s*-\s*", filename)
    if match:
        return match.group(1).strip()

    # Wzorzec: "Artysta Tytuł (Official...) [ID].ext"
    # Weź pierwsze 2-3 słowa jako artystę
    words = filename.split()
    if len(words) >= 3:
        # Szukaj słów kluczowych oddzielających artystę od tytułu
        for i, word in enumerate(words):
            if word.lower() in ("-", "–", "—"):
                return " ".join(words[:i])
    return "Nieznany"


def format_size(size_bytes: int) -> str:
    """Formatuje bajty do czytelnej formy."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024**2:.1f} MB"
    else:
        return f"{size_bytes / 1024**3:.2f} GB"


def count_archive(archive_path: str) -> int:
    """Liczy wpisy w archiwum."""
    if not os.path.exists(archive_path):
        return 0
    with open(archive_path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ============ WYŚWIETLANIE ============

def print_stats(files: list[dict], archive_path: str, detailed: bool = False):
    """Wyświetla statystyki."""
    if not files:
        print("Brak pobranych plików w katalogu.")
        return

    total_size = sum(f["size"] for f in files)
    video_files = [f for f in files if f["is_video"]]
    audio_files = [f for f in files if f["is_audio"]]
    archive_count = count_archive(archive_path)

    # Artystów
    artists = Counter(f["artist"] for f in files)
    top_artists = artists.most_common(15)

    # Formaty
    formats = Counter(f["ext"] for f in files)

    # Ostatnio pobrane
    recent = sorted(files, key=lambda x: x["mtime"], reverse=True)[:10]

    print()
    print("═" * 60)
    print(" 📊 STATYSTYKI POBIERANIA")
    print("═" * 60)
    print()
    print(f"  📁 Pliki ogółem:      {len(files)}")
    print(f"  🎬 Wideo:             {len(video_files)}")
    print(f"  🎵 Audio:             {len(audio_files)}")
    print(f"  💾 Rozmiar łącznie:   {format_size(total_size)}")
    print(f"  📋 W archiwum:        {archive_count} (unikalnych ID)")
    print()

    # Średni rozmiar
    avg_size = total_size / len(files) if files else 0
    print(f"  📐 Średni rozmiar:    {format_size(int(avg_size))}")
    print()

    # Formaty
    print("  📦 Formaty:")
    for ext, count in formats.most_common():
        bar = "█" * min(count, 30)
        print(f"      {ext:6} {count:4} {bar}")
    print()

    # Top artyści
    print(f"  🎤 Top artyści ({len(artists)} unikalnych):")
    for artist, count in top_artists:
        bar = "█" * min(count, 20)
        print(f"      {artist[:25]:25} {count:3} {bar}")
    print()

    # Ostatnio pobrane
    print("  🕐 Ostatnio pobrane:")
    for f in recent:
        date = datetime.fromtimestamp(f["mtime"]).strftime("%Y-%m-%d %H:%M")
        name = f["filename"][:45]
        print(f"      {date}  {name}")
    print()

    if detailed:
        print("─" * 60)
        print(" PEŁNA LISTA:")
        print("─" * 60)
        for i, f in enumerate(sorted(files, key=lambda x: x["filename"]), 1):
            size_str = format_size(f["size"])
            print(f"  {i:3}. [{size_str:>8}] {f['filename'][:60]}")
        print()

    print("═" * 60)


# ============ MAIN ============

def parse_args():
    parser = argparse.ArgumentParser(description="Statystyki pobranych plików")
    parser.add_argument("--dir", default=DEFAULT_DIR,
                        help="Katalog z pobranymi plikami")
    parser.add_argument("--archive", default="pobrane.txt",
                        help="Plik archiwum")
    parser.add_argument("--detailed", action="store_true",
                        help="Pokaż pełną listę plików")
    return parser.parse_args()


def main():
    args = parse_args()
    directory = os.path.abspath(args.dir)
    archive_path = os.path.abspath(args.archive)

    if not os.path.isdir(directory):
        print(f"[BŁĄD] Katalog nie istnieje: {directory}")
        return

    files = scan_files(directory)
    print_stats(files, archive_path, args.detailed)


if __name__ == "__main__":
    main()
