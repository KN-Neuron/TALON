 
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

### [B] Wymagają edycji `main.cpp`

**`main.cpp` nie czyta żadnego pliku konfiguracyjnego** — wartości są zaszyte
jako domyślne pól w strukturach C++. Te parametry są w `config.env` opisane
wraz z **dokładnym numerem linii** do zmiany, a `run.sh` ostrzeże, jeśli
ustawisz je licząc na natychmiastowy efekt:

| Parametr | Domyślnie | Gdzie w kodzie |
| --- | --- | --- |
| Indeks kamery | `0` | `main.cpp:451` |
| Rozdzielczość | `640x480` | `main.cpp:452-453` |
| Kąt widzenia (FOV) | `60.0°` | `main.cpp:436` |
| Próg pewności YOLO | `0.45` | `main.cpp:158` |
| Próg NMS | `0.45` | `main.cpp:159` |
| Próg kojarzenia obiektów | `1.0 m` | `main.cpp:556` |
| Domyślna szerokość obiektu | `0.30 m` | `main.cpp:144` |
| Minimalne pole konturu | `700 px²` | `main.cpp:454` |
| Siatka zajętości | `0.1 m / 10 m` | `main.cpp:489` |

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

> **Uwaga:** program ładuje model ścieżką względną (`main.cpp:483`), dlatego
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
├── main.cpp            # całość logiki: YOLO, geometria, Kalman, BEV
├── include/            # nagłówki pomocnicze
├── models/             # wagi ONNX — pobierane osobno
├── assets/             # obrazy testowe i wyniki
└── classifiers/        # kaskady Haara
```

---

## Czego brakuje i dlaczego

Uczciwa lista ograniczeń — to projekt badawczy, nie gotowy produkt.

### Struktura kodu

- **Wszystko siedzi w jednym `main.cpp`** (~700 linii). Detektor YOLO, filtr
  Kalmana, siatka zajętości i pętla główna to osobne odpowiedzialności, które
  normalnie rozdzieliłoby się na pliki w `include/` i `src/`.
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
  do pliku ani CSV, więc nie ma jak analizować przebiegu po fakcie.
- **Śledzenie metodą najbliższego sąsiada** — proste i szybkie, ale przy
  wielu podobnych obiektach blisko siebie potrafi zamienić ID.

### Inżynieria

- **Brak testów** — żadnych jednostkowych ani integracyjnych. Funkcje czysto
  matematyczne (`calculateDepth`, `calculateX`, krok Kalmana) nadają się do
  testów natychmiast, bo nie zależą od kamery.
- **Brak CI** — nic nie weryfikuje, czy projekt kompiluje się na Linuksie.
- **Tylko CPU** — ścieżka CUDA jest w kodzie, ale zakomentowana
  (`main.cpp:166-167`).

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
