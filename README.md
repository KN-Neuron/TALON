 
                    ___                                 ___
                   /   \                               /   \
              ____|  o  |_____________________________|  o  |____
             /____|_____|_____________________________|_____|____\
                    |                                   |
                    |          ┌─────────────┐          |
                    |          │   ▄▄▄▄▄▄▄   │          |
                    └──────────┤  █ ◉◉◉◉◉ █  ├──────────┘
                               │  █ ◉   ◉ █  │
                               │  █ ◉◉◉◉◉ █  │
                               │   ▀▀▀▀▀▀▀   │
                    ┌──────────┤  ╔═══════╗  ├──────────┐
                    |          │  ║ TALON ║  │          |
                    |          │  ║ ░░░░░ ║  │          |
                    |          │  ╚═══════╝  │          |
                    |          └──────┬──────┘          |
                    |               ╱ │ ╲               |
              _____|_____         ╱   │   ╲         _____|_____
             /___________\       ╱  ╔═╧═╗  ╲       /___________\
              \    |    /       ╱   ║▓▓▓║   ╲      \    |    /
                   |           ╱    ╚═╤═╝    ╲          |
                   ◉          ╱       │       ╲         ◉
                              ════════╧════════
                                   ╲  │  ╱
                                    ╲ │ ╱
                                     ╲│╱
                                      ▼
                              ░ ░ ░ ░ ░ ░ ░
                           ░ ░ ░ ░ ░ ░ ░ ░ ░ ░
                              ░ ░ ░ ░ ░ ░ ░

                    ▶ UNIT-07 ▪ AUTONOMOUS ▪ ARMED ◀


---

## Co to jest

TALON to system **wykrywania przeszkód i szacowania odległości dla drona**,
oparty na monokularnej (pojedynczej) kamerze. Działa w czasie rzeczywistym na
CPU i łączy dwa podejścia:

- **Detekcja obiektów (YOLOv8)** — sieć neuronowa uruchamiana przez OpenCV DNN
  rozpoznaje obiekty z 80 klas zbioru COCO (człowiek, krzesło, butelka…).
- **Klasyczna geometria + filtr Kalmana** — na podstawie znanej rzeczywistej
  szerokości obiektu i jego szerokości w pikselach liczona jest odległość,
  a filtr Kalmana wygładza pomiar i estymuje prędkość zbliżania.

### Jak liczona jest odległość

Przy monokularnej kamerze nie ma bezpośredniej informacji o głębi, więc
korzystamy z podobieństwa trójkątów:

```
Z = fx · W_rzeczywiste / w_piksele
```

gdzie `fx` to ogniskowa w pikselach, wyliczana z kąta widzenia obiektywu:

```
fx = szerokość_obrazu / (2 · tan(FOV / 2))
```

Stąd **kąt widzenia kamery (`h_fov_deg`) jest najważniejszym parametrem
kalibracyjnym** — błędny FOV przekłada się wprost na błędne odległości.

### Co robi program po uruchomieniu

1. Pobiera klatkę z kamery i uruchamia detekcję YOLO.
2. Dla każdej detekcji liczy odległość `Z` i przesunięcie boczne `X`.
3. Kojarzy detekcje ze śledzonymi obiektami (najbliższy sąsiad) i nadaje im
   trwałe ID — obiekt nie „miga”, gdy zniknie na kilka klatek.
4. Filtr Kalmana wygładza pozycję i szacuje prędkość zbliżania.
5. Rysuje dwa okna: **podgląd kamery** z ramkami i **siatkę zajętości (BEV)** —
   widok z góry pokazujący, gdzie są przeszkody.

Wyjście z programu: **ESC**.

---

## Szybki start

```bash
./run.sh
```

Jedna komenda na macOS i Linuksie: wykrywa platformę, sprawdza zależności,
konfiguruje CMake, kompiluje równolegle i uruchamia program z właściwym
katalogiem roboczym.

| Komenda | Działanie |
| --- | --- |
| `./run.sh` | Zbuduj (jeśli trzeba) i uruchom |
| `./run.sh build` | Tylko kompilacja |
| `./run.sh rebuild` | Kompilacja od zera |
| `./run.sh clean` | Usuń katalog `build/` |
| `./run.sh --help` | Pomoc |

### Wymagania

- **CMake** >= 3.16
- **OpenCV 4** (z modułem `dnn`)
- Kompilator z obsługą **C++23**
- Kamera (wbudowana lub USB)

```bash
# macOS
brew install opencv cmake

# Ubuntu / Debian
sudo apt update && sudo apt install libopencv-dev cmake build-essential
```

---

## Konfiguracja

Ustawienia zmieniasz w pliku **`config.env`** (skopiuj wzorzec i odkomentuj
to, czego potrzebujesz):

```bash
cp config.example.env config.env
```

**Czego nie ustawisz, zostaje na wartości domyślnej z kodu.** Plik `config.env`
jest ignorowany przez git, więc twoje lokalne ustawienia nie trafią do repo.

Parametry dzielą się na dwie kategorie — to ważne:

### [A] Działają od razu

Egzekwowane przez `run.sh`:

| Klucz | Domyślnie | Opis |
| --- | --- | --- |
| `MODEL` | `yolov8n.onnx` | Plik modelu w `models/`. Inna nazwa jest podstawiana automatycznie. |
| `MODELS_DIR` | `models` | Katalog z modelami. |
| `BUILD_TYPE` | `Release` | `Release` lub `Debug`. |
| `CMAKE_EXTRA_ARGS` | — | Dodatkowe flagi dla CMake. |

### [B] Wymagają edycji kodu

**Kod nie czyta żadnego pliku konfiguracyjnego** — wartości są zaszyte
jako domyślne pól w strukturach C++. Te parametry są w `config.env` opisane
wraz z **dokładnym numerem linii** do zmiany, a `run.sh` ostrzeże, jeśli
ustawisz je licząc na natychmiastowy efekt:

| Parametr | Domyślnie | Gdzie w kodzie |
| --- | --- | --- |
| Indeks kamery | `0` | `include/Config.hpp:31` |
| Rozdzielczość | `640x480` | `include/Config.hpp:32-33` |
| Kąt widzenia (FOV) | `60.0°` | `include/Config.hpp:16` |
| Próg pewności YOLO | `0.45` | `include/YoloDetector.hpp:59` |
| Próg NMS | `0.45` | `include/YoloDetector.hpp:60` |
| Próg kojarzenia obiektów | `1.0 m` | `src/main.cpp:110` |
| Domyślna szerokość obiektu | `0.30 m` | `src/YoloDetector.cpp:27` |
| Minimalne pole konturu | `700 px²` | `include/Config.hpp:34` |
| Siatka zajętości | `0.1 m / 10 m` | `src/main.cpp:43` |

---

## Modele

Wagi sieci **nie są w repozytorium** (duże pliki binarne — `.gitignore`).
Po sklonowaniu projektu trzeba je pobrać samodzielnie:

```bash
pip install ultralytics
yolo export model=yolov8n.pt format=onnx opset=12
mv yolov8n.onnx models/
```

Wymagany jest format **ONNX**. Pliki `.pt` to wagi PyTorch, których OpenCV DNN
nie wczyta — `run.sh` odmówi uruchomienia i o tym przypomni.

> **Uwaga:** program ładuje model ścieżką względną (`src/main.cpp:37`), dlatego
> `run.sh` uruchamia binarkę z katalogu `models/`. Uruchamiając ręcznie:
> `cd models && ../build/testcv`.

---

## Struktura projektu

```
TALON/
├── run.sh              # jedyny punkt wejścia: build + run
├── config.env          # twoja konfiguracja (ignorowana przez git)
├── config.example.env  # wzorzec konfiguracji (w repo)
├── CMakeLists.txt
├── include/
│   ├── YoloDetector.hpp       # detekcja YOLO + klasy COCO
│   ├── KalmanFilter2D.hpp     # filtr Kalmana + TrackedObject
│   ├── OccupancyGrid2D.hpp    # siatka zajętości (BEV)
│   ├── PerceptionMath.hpp     # geometria: głębia, X, TTC (header-only)
│   ├── DetectionPublisher.hpp # wysyłanie detekcji na gniazdo
│   ├── FrameServer.hpp        # udostępnianie klatek (pamięć współdzielona)
│   └── Config.hpp             # Config + CameraParams (header-only)
├── src/
│   ├── main.cpp               # pętla główna: detekcja → tracking → render
│   ├── YoloDetector.cpp
│   ├── KalmanFilter2D.cpp
│   ├── OccupancyGrid2D.cpp
│   ├── DetectionPublisher.cpp
│   └── FrameServer.cpp
├── tests/
│   └── test_perception_math.cpp  # geometria + Kalman (./run.sh test)
├── models/             # wagi ONNX — pobierane osobno
├── assets/             # obrazy testowe i wyniki
└── classifiers/        # kaskady Haara
```

`PerceptionMath.hpp` i `Config.hpp` nie mają odpowiedników `.cpp` — zawierają
wyłącznie funkcje `inline` i struktury danych, więc implementacja jest w
nagłówku.

---

## Czego brakuje i dlaczego

Uczciwa lista ograniczeń — to projekt badawczy, nie gotowy produkt.

### Struktura kodu

- **Brak wczytywania konfiguracji w kodzie** — dlatego `config.env` obsługuje
  tylko parametry środowiskowe. Dodanie prostego parsera lub `cv::FileStorage`
  odblokowałoby całą sekcję [B] bez rekompilacji.
- **Brak obsługi argumentów CLI** — `main()` nie przyjmuje `argc/argv`, więc nie
  da się wskazać modelu ani kamery z linii poleceń.

### Funkcjonalność

- **Brak trybu offline** — działa wyłącznie z kamery na żywo, nie da się
  puścić pliku wideo ani zdjęcia. To utrudnia powtarzalne testy.
- **Brak kalibracji kamery** — `fx` liczone jest z zakładanego FOV 60°, a nie
  z rzeczywistej kalibracji szachownicą. Odległości są przez to obarczone
  systematycznym błędem, dopóki nie ustawisz własnego FOV.
- **Szacowana szerokość obiektów** — odległość zależy od założonej szerokości
  rzeczywistej, zdefiniowanej tylko dla 4 klas COCO; reszta dostaje 0.30 m.
  Dla nietypowych obiektów pomiar będzie zauważalnie przesunięty.
- **Brak trwałego logowania** — wyniki lecą na `stdout`, nic nie zapisuje się
  do pliku ani CSV, więc nie ma jak analizować przebiegu po fakcie. Ramki
  wysyłane na gniazdo mają komplet danych, więc nagrywanie ich to najprostsza
  droga do powtarzalnych testów.
- **Śledzenie metodą najbliższego sąsiada** — proste i szybkie, ale przy
  wielu podobnych obiektach blisko siebie potrafi zamienić ID.
- **Klatki tylko dla procesów na tym samym urządzeniu** — pamięć współdzielona
  nie przechodzi przez sieć. Odbiorca na innej maszynie musi wziąć obraz ze
  strumienia WebRTC, nie stąd.

### Inżynieria

- **Testy pokrywają tylko matematykę** — `./run.sh test` sprawdza geometrię i
  filtr Kalmana. Detekcja, tracking i pętla główna nie mają pokrycia, bo
  wymagałyby nagrań referencyjnych.
- **Brak CI** — nic nie weryfikuje, czy projekt kompiluje się na Linuksie.
- **Tylko CPU** — ścieżka CUDA jest w kodzie, ale zakomentowana
  (`src/YoloDetector.cpp:36-37`).

---

## Nadawanie detekcji do podglądu na żywo

Program wysyła każdą przetworzoną klatkę jako JSON na gniazdo uniksowe.
Klient streamujący (`apps/client`) czyta te datagramy i przekazuje je kanałem
danych WebRTC, a przeglądarka rysuje ramki na obrazie z kamery.

Nadawanie jest **domyślnie włączone** i nie wymaga niczego dodatkowego —
jeśli po drugiej stronie nikt nie słucha, datagramy po prostu przepadają, a
detekcja działa dalej bez zmian.

```bash
./run.sh                    # nadaje na /tmp/talon-detections.sock
```

### Konfiguracja

| Zmienna | Domyślnie | Znaczenie |
| --- | --- | --- |
| `TALON_DETECTION_SOCKET` | `/tmp/talon-detections.sock` | Ścieżka gniazda. Pusta wartość wyłącza nadawanie. |
| `TALON_ONLY_CLASS` | `39` (butelka) | Klasa COCO do pokazania. `-1` = wszystkie. |

```bash
TALON_ONLY_CLASS=-1 ./run.sh              # wszystkie klasy
TALON_DETECTION_SOCKET= ./run.sh          # bez nadawania, sam podgląd lokalny
```

### Format

Jedna klatka to jeden datagram JSON:

```json
{
  "version": 1,
  "frame_id": 4821,
  "timestamp_ms": 1732104000123,
  "frame_interval_s": 0.033,
  "image_width": 640,
  "image_height": 480,
  "objects": [
    {
      "track_id": 3,
      "class_id": 39,
      "class_name": "bottle",
      "confidence": 0.88,
      "box": { "left": 100, "top": 120, "width": 40, "height": 110 },
      "position": { "lateral_m": -0.45, "forward_m": 2.34 },
      "closing_speed_mps": -0.8,
      "time_to_collision_s": 2.9,
      "frames_since_seen": 0
    }
  ]
}
```

Pełny opis pól: `docs/detection-protocol.md`.

Kilka rzeczy, które warto wiedzieć przy pisaniu odbiorcy:

- **`SOCK_DGRAM`**, więc jedno `sendto` to jedna kompletna wiadomość — nie
  trzeba doklejać długości ani sklejać fragmentów.
- **Nadawanie nie blokuje** (`MSG_DONTWAIT`). Gdy odbiorca nie nadąża, jądro
  gubi datagramy zamiast wstrzymywać pętlę detekcji.
- **`position` i `time_to_collision_s` bywają pominięte** — TTC nie ma sensu
  dla obiektu, który się nie zbliża, więc pole wtedy nie występuje. Odbiorca
  musi to obsłużyć.
- **Ślady na przewidywaniu też są wysyłane**, z rosnącym `frames_since_seen`.
  Obiekt chwilowo zgubiony przez YOLO nie znika natychmiast z podglądu.
- **Pusta lista `objects` jest wysyłana normalnie** — to pozwala odróżnić
  „nic nie widać" od „producent przestał nadawać".

---

## Udostępnianie klatek (moduł jako źródło obrazu)

Ten program jest **właścicielem kamery**. Inne procesy nie otwierają jej
same — podłączają się tutaj i czytają gotowe klatki z pamięci współdzielonej.
Dzięki temu urządzenie jest otwarte dokładnie raz, a odbiorcy dostają obraz,
na którym detekcja już poszła.

Publikowane są dwa strumienie:

| Segment | Zawartość |
| --- | --- |
| `/talon.raw` | czysty obraz z kamery |
| `/talon.annotated` | ten sam obraz z naniesionymi ramkami i etykietami |

Odbiorca wybiera ten, który mu pasuje. Front rysujący własną nakładkę bierze
`raw` (ma dane detekcji z gniazda); podgląd bez własnej logiki bierze
`annotated`.

### Jak to działa

Bufor cykliczny na 4 klatki. Każdy slot ma licznik `sequence`: nieparzysty
oznacza zapis w toku, parzysty — klatkę kompletną. Czytelnik zapamiętuje
licznik, kopiuje piksele i sprawdza licznik ponownie; jeśli się zmienił,
odrzuca kopię i próbuje jeszcze raz.

Nic się nie blokuje. Producent nigdy nie czeka na odbiorcę, a wolny odbiorca
gubi klatki zamiast spowalniać detekcję — dla podglądu na żywo to właściwy
kompromis, bo nieaktualna klatka i tak jest bezwartościowa.

Klatka 640x480 BGR to ~920 KB; przy 30 fps daje 27 MB/s. Przez gniazdo każdy
bajt przeszedłby przez jądro dwa razy — tutaj odbiorca sięga wprost do tych
samych stron pamięci. Cena: **oba procesy muszą działać na tym samym
urządzeniu**.

### Odbiór z Pythona

Gotowy czytelnik jest w `apps/client/frame_shm.py`:

```python
from frame_shm import FrameReader

with FrameReader("raw") as reader:      # albo "annotated"
    frame = reader.read()
    if frame is not None:
        frame.image        # numpy BGR, (wysokość, szerokość, 3)
        frame.frame_id     # rosnący numer klatki
        frame.timestamp_ms # czas publikacji
```

`read()` zwraca `None`, gdy trafi na klatkę w trakcie zapisu — to normalne,
wystarczy spróbować ponownie.

### Odbiór z innego języka

Układ pamięci opisuje `include/FrameServer.hpp`. Segment POSIX (`shm_open`)
zaczyna się nagłówkiem `SegmentHeader`, po nim — wyrównane do strony — idą
sloty, każdy z `SlotHeader` i surowymi pikselami BGR.

Pole `layout_version` w nagłówku pozwala odbiorcy odmówić podłączenia, gdy
układ się rozjedzie — lepiej to niż interpretowanie bajtów po swojemu.

### Konfiguracja

| Zmienna | Domyślnie | Znaczenie |
| --- | --- | --- |
| `TALON_SHARE_FRAMES` | `1` | `0` wyłącza udostępnianie klatek. |

---

## Uruchomienie całości

```bash
cd apps/backend && go run ./cmd/server     # 1. relay
./run.sh                                   # 2. percepcja (ten program)
cd apps/client && uv run main.py           # 3. streaming
cd apps/frontend && npm run dev            # 4. podgląd
```

Kolejność ma znaczenie: moduł percepcji tworzy segment pamięci, klient tylko
się podłącza. Uruchomiony wcześniej klient nie znajdzie segmentu i przejdzie
na własną kamerę (`video_source=auto`), co zablokuje kamerę modułowi.

Klienta konfiguruje `apps/client/.env`:

```
VIDEO_SOURCE=perception    # auto | perception | local
FRAME_STREAM=raw           # raw | annotated
```

`auto` (domyślne) próbuje modułu, a gdy go nie ma — otwiera własną kamerę.
`perception` wymaga modułu i nie próbuje kamery, co jest bezpieczniejsze na
dronie: cichy fallback maskowałby to, że percepcja nie działa.

---

## Znane problemy

**macOS: `Błąd otwarcia kamery!`** — system wymaga zgody na dostęp do kamery
dla aplikacji uruchamiającej program (terminal / IDE). Nadaj ją w:
*Ustawienia systemowe → Prywatność i ochrona → Kamera*, a potem uruchom
terminal ponownie.

**Linux: brak dostępu do `/dev/video0`** — dodaj użytkownika do grupy `video`:
```bash
sudo usermod -aG video $USER
```
(wymaga wylogowania i zalogowania).
