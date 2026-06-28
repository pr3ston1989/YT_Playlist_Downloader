"""
Skrypt do mergowania już pobranych plików (webm audio + mp4 video) do MKV.
Uruchom po zainstalowaniu ffmpeg.exe w katalogu.

Użycie:
    python merge_existing.py

Szuka par plików z tym samym ID ([VIDEO_ID]) — merguje do MKV i usuwa oryginały.
"""

import os
import subprocess
import re
import glob

FFMPEG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe")
WORK_DIR = os.path.dirname(os.path.abspath(__file__))


def find_pairs():
    """Znajduje pary plików: video (.mp4) + audio (.webm) z tym samym ID."""
    # Wzorzec: nazwa [VIDEO_ID].fXXX.mp4 / .webm
    video_files = glob.glob(os.path.join(WORK_DIR, "*.mp4"))
    audio_files = glob.glob(os.path.join(WORK_DIR, "*.webm"))

    # Wyciągnij ID z nazwy pliku: [ID].fXXX.ext
    id_pattern = re.compile(r'\[([a-zA-Z0-9_-]+)\]\.f\d+\.(mp4|webm)$')

    videos_by_id = {}
    audios_by_id = {}

    for f in video_files:
        basename = os.path.basename(f)
        match = id_pattern.search(basename)
        if match:
            vid_id = match.group(1)
            videos_by_id[vid_id] = f

    for f in audio_files:
        basename = os.path.basename(f)
        match = id_pattern.search(basename)
        if match:
            vid_id = match.group(1)
            audios_by_id[vid_id] = f

    pairs = []
    for vid_id in videos_by_id:
        if vid_id in audios_by_id:
            # Nazwa wyjściowa: tytuł [ID].mkv
            video_path = videos_by_id[vid_id]
            basename = os.path.basename(video_path)
            # Usuń .fXXX.mp4 z końca i dodaj .mkv
            output_name = re.sub(r'\.f\d+\.mp4$', '.mkv', basename)
            pairs.append({
                "id": vid_id,
                "video": videos_by_id[vid_id],
                "audio": audios_by_id[vid_id],
                "output": os.path.join(WORK_DIR, output_name),
            })

    return pairs


def find_subtitles(video_id):
    """Znajduje pliki napisów (.vtt) dla danego ID."""
    pattern = os.path.join(WORK_DIR, f"*[{video_id}]*.vtt")
    return glob.glob(pattern)


def merge_pair(pair):
    """Merguje parę video+audio do MKV z ffmpeg, dołącza napisy jeśli są."""
    if os.path.exists(pair["output"]):
        print(f"  [POMINIĘTO] {os.path.basename(pair['output'])} już istnieje")
        return True

    # Znajdź napisy
    subs = find_subtitles(pair["id"])

    cmd = [FFMPEG, "-y"]
    cmd.extend(["-i", pair["video"]])
    cmd.extend(["-i", pair["audio"]])

    # Dodaj napisy
    for sub in subs:
        cmd.extend(["-i", sub])

    # Mapowanie strumieni
    cmd.extend(["-map", "0:v", "-map", "1:a"])
    for i in range(len(subs)):
        cmd.extend(["-map", str(i + 2)])

    cmd.extend(["-c:v", "copy", "-c:a", "copy"])

    if subs:
        cmd.extend(["-c:s", "srt"])

    cmd.append(pair["output"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  [BŁĄD] {e}")
        return False


def main():
    if not os.path.exists(FFMPEG):
        print(f"[BŁĄD] Nie znaleziono ffmpeg.exe w: {FFMPEG}")
        print("       Pobierz z https://www.gyan.dev/ffmpeg/builds/ (essentials)")
        return

    pairs = find_pairs()
    print(f"[INFO] Znaleziono {len(pairs)} par do zmergowania.")

    if not pairs:
        print("       Brak plików do mergowania.")
        return

    success = 0
    for i, pair in enumerate(pairs, 1):
        title = os.path.basename(pair["output"])[:60]
        print(f"[{i}/{len(pairs)}] {title}...")

        if merge_pair(pair):
            success += 1
            print(f"  OK — usuwam oryginały")
            # Usuń oryginalne pliki
            os.remove(pair["video"])
            os.remove(pair["audio"])
            # Usuń napisy (już osadzone w MKV)
            for sub in find_subtitles(pair["id"]):
                os.remove(sub)
        else:
            print(f"  BŁĄD — zachowuję oryginały")

    print(f"\n[PODSUMOWANIE] Zmergowano: {success}/{len(pairs)}")


if __name__ == "__main__":
    main()
