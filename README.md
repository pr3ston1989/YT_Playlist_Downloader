# YT Playlist Downloader

Skrypt Python do pobierania pełnych playlist YouTube, obchodzący limit 100 pozycji w `yt-dlp`.

## Problem

`yt-dlp` przy bezpośrednim pobieraniu playlisty czasami ogranicza się do pierwszych 100 filmów. Ten skrypt rozwiązuje problem, pobierając najpierw pełną listę URL-i, a następnie ściągając każdy film osobno.

## Wymagania

- Python 3.9+
- `yt-dlp.exe` w katalogu skryptu (lub w PATH)
- `ffmpeg.exe` w katalogu skryptu (do mergowania audio+video i osadzania napisów)
- (opcjonalnie) klucz YouTube Data API v3 — dla playlist >100 pozycji, jeśli `--flat-playlist` nie zwraca pełnej listy

## Użycie

```bash
python download_playlist.py
```

## Konfiguracja

Edytuj sekcję `KONFIGURACJA` w `download_playlist.py`:

| Zmienna | Opis | Domyślnie |
|---------|------|-----------|
| `PLAYLIST_URL` | URL playlisty YouTube | — |
| `OUTPUT_DIR` | Katalog docelowy | `.` |
| `ARCHIVE_FILE` | Plik z listą pobranych filmów | `pobrane.txt` |
| `FFMPEG_LOCATION` | Ścieżka do ffmpeg | `.` |
| `FORMAT` | Format wideo | `bestvideo+bestaudio/best` |
| `MERGE_FORMAT` | Format kontenera | `mkv` |
| `SUB_LANGS` | Języki napisów | `pl,en` |
| `DELAY_BETWEEN_DOWNLOADS` | Opóźnienie między pobieraniami (s) | `2` |
| `USE_YOUTUBE_API` | Użyj YouTube Data API zamiast flat-playlist | `False` |
| `YOUTUBE_API_KEY` | Klucz API (jeśli USE_YOUTUBE_API=True) | — |

## Jak to działa

1. Pobiera listę wszystkich filmów z playlisty (`--flat-playlist` lub YouTube Data API)
2. Sprawdza plik archiwum (`pobrane.txt`) i pomija już pobrane
3. Pobiera każdy film osobno z pełnymi opcjami (napisy, mergowanie do MKV)
4. Zapisuje listę niepowodzeń do `failed_downloads.txt`
5. Można uruchomić wielokrotnie — automatycznie wznawia od miejsca, w którym skończył

## YouTube Data API (opcjonalnie)

Jeśli `--flat-playlist` zwraca max 100 pozycji, możesz użyć YouTube Data API:

1. Wejdź na [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Utwórz projekt i włącz **YouTube Data API v3**
3. Wygeneruj klucz API
4. Wpisz klucz w `YOUTUBE_API_KEY` i ustaw `USE_YOUTUBE_API = True`
5. Zainstaluj requests: `pip install requests`
