# 🎬 YT Playlist Downloader

Zestaw skryptów Python do pobierania teledysków z YouTube:
- **Playlisty** — z obejściem limitu 100 pozycji, paskiem postępu, równoległym pobieraniem
- **Wyszukiwanie po artyście** — automatyczne wyszukiwanie i pobieranie teledysków wykonawcy

---

## 📋 Spis treści

- [Wymagania](#wymagania)
- [Instalacja](#instalacja)
- [Pobieranie playlisty](#pobieranie-playlisty)
- [Pobieranie po artyście](#pobieranie-po-artyście)
- [Mergowanie istniejących plików](#mergowanie-istniejących-plików)
- [Konfiguracja (.env)](#konfiguracja-env)
- [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Wymagania

| Komponent | Wymagany | Do czego |
|-----------|----------|----------|
| Python 3.9+ | ✅ | Uruchomienie skryptów |
| yt-dlp.exe | ✅ | Pobieranie filmów z YouTube |
| ffmpeg.exe | ✅ | Mergowanie audio+video do MKV, osadzanie napisów |
| requests | ❌ opcjonalny | YouTube Data API (pip install requests) |
| ytmusicapi | ❌ opcjonalny | Wyszukiwanie po artyście w YouTube Music (pip install ytmusicapi) |

---

## Instalacja

1. Pobierz lub sklonuj repozytorium:
   ```bash
   git clone https://github.com/pr3ston1989/YT_Playlist_Downloader.git
   cd YT_Playlist_Downloader
   ```

2. Pobierz [yt-dlp](https://github.com/yt-dlp/yt-dlp/releases) i wrzuć `yt-dlp.exe` do folderu projektu.

3. Pobierz [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (wersja "essentials") i wrzuć `ffmpeg.exe` do folderu projektu.

4. (Opcjonalnie) Utwórz plik `.env` z kluczem YouTube Data API:
   ```
   YOUTUBE_API_KEY=twoj_klucz_api
   ```

---

## Pobieranie playlisty

### Podstawowe użycie

```bash
# Pobierz całą playlistę (najlepsza jakość, MKV, napisy PL/EN)
python download_playlist.py "https://www.youtube.com/playlist?list=PLxxxxx"
```

### Wszystkie opcje

```bash
python download_playlist.py "URL" [opcje]
```

| Opcja | Skrót | Opis | Domyślnie |
|-------|-------|------|-----------|
| `--output-dir ŚCIEŻKA` | `-o` | Katalog docelowy na pobrane pliki | `.` (aktualny) |
| `--archive PLIK` | `-a` | Plik z listą pobranych (zapobiega duplikatom) | `pobrane.txt` |
| `--delay SEKUNDY` | `-d` | Opóźnienie między pobieraniami | `2` |
| `--parallel N` | `-p` | Liczba równoległych pobierań | `1` |
| `--retries N` | `-r` | Ile razy ponowić przy błędzie | `3` |
| `--cookies PLIK` | `-c` | Plik cookies (dla prywatnych playlist) | — |
| `--cookies-from-browser NAZWA` | | Pobierz cookies z przeglądarki | — |
| `--use-api` | | Wymuś użycie YouTube Data API | wyłączone |
| `--api-key KLUCZ` | | Klucz YouTube Data API v3 | z .env |
| `--audio-only` | | Pobieraj tylko audio (MP3) | wyłączone |
| `--min-duration SEK` | | Minimalna długość filmu (sekundy) | — |
| `--max-duration SEK` | | Maksymalna długość filmu (sekundy) | — |
| `--export-urls PLIK` | | Eksportuj listę URL bez pobierania | — |
| `--log PLIK` | | Zapisz log sesji do pliku | — |
| `--no-beep` | | Wyłącz dźwięk po zakończeniu | wyłączone |

### Przykłady użycia

```bash
# Standardowe pobieranie z paskiem postępu
python download_playlist.py "https://www.youtube.com/playlist?list=PLxxxxx"

# 3 filmy równolegle (szybsze, ale więcej obciążenia sieci)
python download_playlist.py "URL" --parallel 3

# Tylko audio w MP3 (bez wideo)
python download_playlist.py "URL" --audio-only

# Pomijaj filmy krótsze niż 1 min i dłuższe niż 10 min
python download_playlist.py "URL" --min-duration 60 --max-duration 600

# Pobierz do konkretnego folderu
python download_playlist.py "URL" --output-dir "D:\Muzyka\Playlista"

# Eksportuj listę URL bez pobierania (do późniejszego użycia)
python download_playlist.py "URL" --export-urls lista_filmow.txt

# Logowanie całej sesji do pliku
python download_playlist.py "URL" --log sesja_2024.log

# Prywatna playlista (z cookies z Chrome)
python download_playlist.py "URL" --cookies-from-browser chrome

# Agresywne retry (5 prób) i bez dźwięku
python download_playlist.py "URL" --retries 5 --no-beep

# Wszystko naraz: równolegle, audio, filtr, log
python download_playlist.py "URL" -p 3 --audio-only --min-duration 60 --log sesja.log
```

### Funkcje

| Funkcja | Opis |
|---------|------|
| **Obejście limitu 100** | Automatyczna paginacja po 50 pozycji gdy playlista >100 |
| **Pasek postępu** | Wyświetla %, prędkość i ETA dla każdego pobieranego filmu |
| **Równoległe pobieranie** | `--parallel N` uruchamia N wątków jednocześnie |
| **Retry z backoff** | Przy błędzie próbuje ponownie (rosnące opóźnienie: 5s, 10s, 15s) |
| **Archiwum globalne** | Jeden plik `pobrane.txt` dla wszystkich playlist — nigdy nie pobiera dwa razy |
| **Wznawianie** | Ctrl+C w dowolnym momencie, uruchom ponownie = kontynuacja |
| **Kolorowy output** | Zielone ✓ sukces, czerwone ✗ błąd, żółte ostrzeżenia |
| **ETA** | Szacowany czas pozostały na bazie średniego tempa pobierania |
| **Powiadomienie dźwiękowe** | Beep po zakończeniu (wyłącz: `--no-beep`) |
| **YouTube Data API fallback** | Jeśli yt-dlp zwraca ≤100, automatycznie próbuje API |
| **Napisy** | Pobiera i osadza napisy (priorytet: polski, angielski) |
| **Najlepsza jakość** | `bestvideo+bestaudio` mergowane do MKV |

---

## Pobieranie po artyście

### Podstawowe użycie

```bash
# Wyszukaj i pobierz teledyski Metalliki (domyślnie 30)
python download_artist.py "Metallica"
```

### Wszystkie opcje

| Opcja | Skrót | Opis | Domyślnie |
|-------|-------|------|-----------|
| `--max-results N` | `-n` | Maks. wyników wyszukiwania | `30` |
| `--output-dir ŚCIEŻKA` | `-o` | Katalog docelowy | `.` |
| `--archive PLIK` | `-a` | Plik archiwum | `pobrane.txt` |
| `--delay SEK` | `-d` | Opóźnienie (sekundy) | `2` |
| `--use-ytmusic` | | Użyj YouTube Music API | wyłączony |
| `--list-only` | | Tylko wyświetl, nie pobieraj | wyłączony |

### Przykłady

```bash
# Wyszukaj i pobierz teledyski
python download_artist.py "Rammstein"

# Więcej wyników (50 zamiast 30)
python download_artist.py "Daft Punk" --max-results 50

# Tylko podejrzyj co znalazł (bez pobierania)
python download_artist.py "Radiohead" --list-only

# Użyj YouTube Music (lepsza dyskografia, wymaga pip install ytmusicapi)
python download_artist.py "BLACKPINK" --use-ytmusic

# Pobierz do osobnego folderu
python download_artist.py "Queen" -o "D:\Muzyka\Queen"
```

### Jak filtruje teledyski

Skrypt szuka `"artysta official music video"` i rankinguje wyniki:
- **+10 pkt** — tytuł zawiera "official music video", "official video", "teledysk"
- **+5 pkt** — tytuł zawiera "official"
- **+3 pkt** — kanał pasuje do artysty (oficjalny kanał)
- **+2 pkt** — pełna nazwa artysty w tytule
- **-3 pkt** — "lyrics video" (niższy priorytet)
- **-4 pkt** — "audio only" (niższy priorytet)
- **Odrzuca** — live, cover, reaction, karaoke, tutorial, wywiad

---

## Mergowanie istniejących plików

Jeśli pobrano pliki bez ffmpeg (osobne .mp4 i .webm):

```bash
python merge_existing.py
```

Skrypt:
1. Znajduje pary plików z tym samym video ID
2. Merguje video (mp4) + audio (webm) do jednego MKV
3. Dołącza napisy (jeśli są pliki .vtt)
4. Usuwa oryginalne pliki po udanym mergu

**Wymaga:** `ffmpeg.exe` w folderze projektu.

---

## Konfiguracja (.env)

Utwórz plik `.env` w folderze projektu:

```env
# Klucz YouTube Data API v3
# Pobierz z: https://console.cloud.google.com/apis/credentials
# Włącz: YouTube Data API v3
YOUTUBE_API_KEY=AIzaSy...

# Możesz dodać więcej zmiennych w przyszłości
```

Klucz API jest opcjonalny — skrypt działa bez niego, ale z kluczem automatycznie obchodzi limit 100 pozycji przez API.

---

## Rozwiązywanie problemów

### "yt-dlp nie znaleziony"
- Upewnij się, że `yt-dlp.exe` jest w folderze projektu lub w PATH.

### Pliki pobierają się osobno (mp4 + webm)
- Brak `ffmpeg.exe` w folderze. Pobierz z https://www.gyan.dev/ffmpeg/builds/
- Po dodaniu ffmpeg uruchom `python merge_existing.py` żeby zmergować istniejące.

### Limit 100 filmów
- Skrypt automatycznie próbuje paginację i API fallback.
- Jeśli playlista jest prywatna, użyj `--cookies-from-browser chrome`.

### "No supported JavaScript runtime"
- To ostrzeżenie z nowej wersji yt-dlp. Zainstaluj [Deno](https://deno.land/) lub zignoruj — większość filmów pobiera się normalnie.

### Błąd kodowania (UnicodeDecodeError)
- Naprawione — skrypt używa `errors="replace"` dla nietypowych znaków.

### Prywatna/niepubliczna playlista
```bash
python download_playlist.py "URL" --cookies-from-browser chrome
```
Użyj nazwy przeglądarki, w której jesteś zalogowany na YouTube.

### Pobieranie jest wolne
- Spróbuj `--parallel 3` (3 filmy naraz)
- YouTube może throttlować — zmniejsz `--delay 1`

---

## Struktura projektu

```
YT_Playlist_Downloader/
├── download_playlist.py   # Główny skrypt — pobieranie playlist
├── download_artist.py     # Wyszukiwanie i pobieranie po artyście
├── merge_existing.py      # Mergowanie osobnych plików mp4+webm
├── .env                   # Klucz API (nie commitowany)
├── .gitignore             # Ignorowane pliki
├── README.md              # Ten plik
├── pobrane.txt            # Archiwum pobranych (nie commitowane)
├── yt-dlp.exe             # Binarka yt-dlp (nie commitowana)
└── ffmpeg.exe             # Binarka ffmpeg (nie commitowana)
```

---

## Licencja

Projekt do użytku prywatnego. Pamiętaj o prawach autorskich do pobieranych treści.
