# YT Playlist Downloader

Skrypty Python do pobierania muzyki z YouTube:
- **Playlisty** (obejście limitu 100 pozycji w yt-dlp)
- **Wyszukiwanie po artyście** (pobieranie teledysków danego wykonawcy)

## Problem

`yt-dlp` przy bezpośrednim pobieraniu playlisty czasami ogranicza się do pierwszych 100 filmów. Ten skrypt rozwiązuje problem, pobierając najpierw pełną listę URL-i, a następnie ściągając każdy film osobno.

## Wymagania

- Python 3.9+
- `yt-dlp.exe` w katalogu skryptu (lub w PATH)
- `ffmpeg.exe` w katalogu skryptu (do mergowania audio+video i osadzania napisów)
- (opcjonalnie) `pip install ytmusicapi` — dla wyszukiwania po artyście w YouTube Music
- (opcjonalnie) klucz YouTube Data API v3 — dla playlist >100 pozycji, jeśli `--flat-playlist` nie zwraca pełnej listy

## Użycie

```bash
python download_playlist.py "https://www.youtube.com/playlist?list=PLxxxxx"
```

Opcjonalne argumenty:

```bash
python download_playlist.py "URL" --output-dir ./filmy --archive pobrane.txt --delay 3
python download_playlist.py "URL" --use-api --api-key TWOJ_KLUCZ
```

| Argument | Opis | Domyślnie |
|----------|------|-----------|
| `url` (pozycyjny) | URL playlisty YouTube | wymagany |
| `--output-dir`, `-o` | Katalog docelowy | `.` |
| `--archive`, `-a` | Plik archiwum pobranych | `pobrane.txt` |
| `--delay`, `-d` | Opóźnienie między pobieraniami (s) | `2` |
| `--use-api` | Użyj YouTube Data API | wyłączony |
| `--api-key` | Klucz YouTube Data API v3 | — |

## Funkcje

- **Najlepsza jakość** — `bestvideo+bestaudio/best`, mergowane do MKV
- **Napisy** — pobierane i osadzane w pliku (priorytet: pl, en)
- **Archiwum** — jeden globalny plik `pobrane.txt` zapobiega ponownemu pobieraniu nawet z innej playlisty
- **Wznawianie** — Ctrl+C w dowolnym momencie, ponowne uruchomienie kontynuuje od miejsca przerwania
- **Obsługa >100 filmów** — lista URL wyciągana osobno, pobieranie pojedynczo

## Jak to działa

1. Pobiera listę wszystkich filmów z playlisty (`--flat-playlist` lub YouTube Data API)
2. Sprawdza plik archiwum (`pobrane.txt`) i pomija już pobrane
3. Pobiera każdy film osobno z pełnymi opcjami (napisy, mergowanie do MKV)
4. Zapisuje listę niepowodzeń do `failed_downloads.txt`
5. Można uruchomić wielokrotnie — automatycznie wznawia od miejsca, w którym skończył

## Pobieranie po artyście

```bash
# Wyszukaj i pobierz teledyski artysty (domyślnie 30 wyników)
python download_artist.py "Metallica"

# Więcej wyników
python download_artist.py "Rammstein" --max-results 50

# Tylko wyświetl co znalazł (bez pobierania)
python download_artist.py "Daft Punk" --list-only

# Użyj YouTube Music (lepsza dyskografia, wymaga ytmusicapi)
python download_artist.py "Radiohead" --use-ytmusic
```

| Argument | Opis | Domyślnie |
|----------|------|-----------|
| `artist` (pozycyjny) | Nazwa artysty/zespołu | wymagany |
| `--max-results`, `-n` | Maks. wyników wyszukiwania | `30` |
| `--output-dir`, `-o` | Katalog docelowy | `.` |
| `--archive`, `-a` | Plik archiwum | `pobrane.txt` |
| `--delay`, `-d` | Opóźnienie (s) | `2` |
| `--use-ytmusic` | Użyj YouTube Music API | wyłączony |
| `--list-only` | Tylko wyświetl, nie pobieraj | wyłączony |

**Tryb domyślny** (`ytsearch`) szuka na YouTube "`Artysta official music video`" — dobrze trafia w teledyski.

**Tryb `--use-ytmusic`** przeszukuje YouTube Music i zwraca oficjalne utwory z profilu artysty (lepsza precyzja, wymaga `pip install ytmusicapi`).

## YouTube Data API (opcjonalnie)

Jeśli `--flat-playlist` zwraca max 100 pozycji, możesz użyć YouTube Data API:

1. Wejdź na [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Utwórz projekt i włącz **YouTube Data API v3**
3. Wygeneruj klucz API
4. Wpisz klucz w `YOUTUBE_API_KEY` i ustaw `USE_YOUTUBE_API = True`
5. Zainstaluj requests: `pip install requests`
