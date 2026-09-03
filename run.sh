#!/usr/bin/env bash
#
# TALON - jeden skrypt do wszystkiego (macOS + Linux).
#
#   ./run.sh          buduje (jesli trzeba) i uruchamia
#   ./run.sh build    tylko buduje
#   ./run.sh test     buduje i uruchamia testy jednostkowe
#   ./run.sh clean    czysci katalog build/
#   ./run.sh rebuild  czysci i buduje od zera
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$ROOT/build"
BIN_NAME="testcv"

# Nazwa, pod ktora main.cpp:483 laduje model (na sztywno w kodzie).
HARDCODED_MODEL="yolov8n.onnx"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

# --- Konfiguracja ----------------------------------------------------------
# Wartosci domyslne; config.env moze je nadpisac.
MODEL="$HARDCODED_MODEL"
MODELS_DIR_NAME="models"
BUILD_TYPE="Release"
CMAKE_EXTRA_ARGS=""

# Przekazywane programowi przez srodowisko (main.cpp czyta je getenv()).
# Pusta wartosc = nie ustawiamy, program uzyje swojej domyslnej.
DETECTION_SOCKET=""
ONLY_CLASS=""
SHARE_FRAMES=""
DETECTION_SOCKET_SET=0

CONFIG_FILE="$ROOT/config.env"

load_config() {
  [ -f "$CONFIG_FILE" ] || return 0

  # Parsujemy recznie (bez `source`), zeby plik konfiguracyjny nie mogl
  # wykonac dowolnego kodu.
  local line key val
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"                        # usun komentarz
    line="$(printf '%s' "$line" | tr -d '\r')"
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"; val="${line#*=}"
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    val="$(printf '%s' "$val" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/^"\(.*\)"$/\1/; s/^'"'"'\(.*\)'"'"'$/\1/')"
    # TALON_DETECTION_SOCKET= (pusta wartosc) swiadomie wylacza nadawanie,
    # wiec dla tego klucza pusta wartosc jest poprawna.
    if [ "$key" = "TALON_DETECTION_SOCKET" ] && [ -z "$val" ]; then
      DETECTION_SOCKET=""; DETECTION_SOCKET_SET=1; continue
    fi
    [ -n "$key" ] && [ -n "$val" ] || continue

    case "$key" in
      MODEL)            MODEL="$val" ;;
      TALON_DETECTION_SOCKET) DETECTION_SOCKET="$val"; DETECTION_SOCKET_SET=1 ;;
      TALON_ONLY_CLASS)       ONLY_CLASS="$val" ;;
      TALON_SHARE_FRAMES)     SHARE_FRAMES="$val" ;;
      MODELS_DIR)       MODELS_DIR_NAME="$val" ;;
      BUILD_TYPE)       BUILD_TYPE="$val" ;;
      CMAKE_EXTRA_ARGS) CMAKE_EXTRA_ARGS="$val" ;;
      # Parametry algorytmu — main.cpp ich nie czyta (patrz config.env [B]).
      CAM_INDEX|CAM_WIDTH|CAM_HEIGHT|CAM_HFOV_DEG|CONF_THRESHOLD|NMS_THRESHOLD|\
      MATCH_THRESHOLD|DEFAULT_REAL_WIDTH|MIN_AREA|GRID_CELL_SIZE|GRID_MAX_RANGE)
        CODE_ONLY_KEYS="${CODE_ONLY_KEYS:-}$key " ;;
      *) warn "config.env: nieznany klucz '$key' — pomijam." ;;
    esac
  done < "$CONFIG_FILE"
}

# Ostrzez, jesli ktos ustawil parametr, ktorego binarka nie odczyta.
warn_code_only() {
  [ -n "${CODE_ONLY_KEYS:-}" ] || return 0
  warn "Te parametry z config.env wymagaja edycji main.cpp (kod nie czyta konfiguracji):"
  local k
  for k in $CODE_ONLY_KEYS; do printf '      - %s\n' "$k" >&2; done
  warn "Dokladne numery linii sa w komentarzach w config.env."
}

# --- Wykrycie platformy i podpowiedz instalacyjna -------------------------
platform_hint() {
  case "$(uname -s)" in
    Darwin) echo "brew install cmake opencv" ;;
    Linux)
      if   command -v apt-get >/dev/null 2>&1; then echo "sudo apt install cmake build-essential libopencv-dev"
      elif command -v dnf     >/dev/null 2>&1; then echo "sudo dnf install cmake gcc-c++ opencv-devel"
      elif command -v pacman  >/dev/null 2>&1; then echo "sudo pacman -S cmake base-devel opencv"
      else echo "zainstaluj: cmake, kompilator C++, OpenCV 4 (dev)"; fi ;;
    *) echo "zainstaluj: cmake, kompilator C++, OpenCV 4 (dev)" ;;
  esac
}

check_deps() {
  command -v cmake >/dev/null 2>&1 || die "Brak cmake. Zainstaluj: $(platform_hint)"
  command -v cmake >/dev/null 2>&1 || true
  # Generator: preferuj ninja, jesli jest (szybciej), inaczej domyslny make.
  if command -v ninja >/dev/null 2>&1; then GENERATOR=(-G Ninja); else GENERATOR=(); fi
}

# --- Liczba rdzeni, przenosnie --------------------------------------------
jobs_count() {
  if   command -v nproc          >/dev/null 2>&1; then nproc
  elif command -v sysctl         >/dev/null 2>&1; then sysctl -n hw.ncpu
  else echo 4; fi
}

# clangd (nvim/VSCode) szuka compile_commands.json w korzeniu projektu,
# a CMake generuje go w build/. Podlinkowujemy, zeby LSP nie zglaszal
# falszywych bledow o brakujacych naglowkach OpenCV.
link_compile_commands() {
  local src="$BUILD_DIR/compile_commands.json"
  [ -f "$src" ] || return 0
  if [ -e "$ROOT/compile_commands.json" ] && [ ! -L "$ROOT/compile_commands.json" ]; then
    return 0   # nie nadpisujemy prawdziwego pliku uzytkownika
  fi
  ln -sfn "build/compile_commands.json" "$ROOT/compile_commands.json"
}

do_build() {
  check_deps
  info "Konfiguracja (CMake, ${BUILD_TYPE})..."
  # shellcheck disable=SC2086
  cmake -S "$ROOT" -B "$BUILD_DIR" "${GENERATOR[@]}" \
    -DCMAKE_BUILD_TYPE="$BUILD_TYPE" $CMAKE_EXTRA_ARGS \
    || die "Konfiguracja nie powiodla sie. Czy OpenCV 4 jest zainstalowane? $(platform_hint)"

  info "Kompilacja..."
  cmake --build "$BUILD_DIR" --parallel "$(jobs_count)" \
    || die "Kompilacja nie powiodla sie."

  link_compile_commands
  info "Gotowe: $BUILD_DIR/$BIN_NAME"
}

find_binary() {
  # Ninja/Make kladzie binarke w build/, ale multi-config generatory w build/Release/.
  for c in "$BUILD_DIR/$BIN_NAME" "$BUILD_DIR/Release/$BIN_NAME" "$BUILD_DIR/Debug/$BIN_NAME"; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

do_run() {
  local bin models_dir link_made=0
  bin="$(find_binary)" || die "Nie znaleziono binarki. Uruchom: ./run.sh build"
  models_dir="$ROOT/$MODELS_DIR_NAME"

  [ -d "$models_dir" ] || die "Brak katalogu '$MODELS_DIR_NAME/'."
  [ -f "$models_dir/$MODEL" ] || die \
"Brak modelu: $MODELS_DIR_NAME/$MODEL
    Pobierz go i umiesc w tym katalogu (instrukcja w README, sekcja 'Modele')."

  case "$MODEL" in
    *.onnx) ;;
    *) die "Model musi byc w formacie ONNX (.onnx). Podano: $MODEL
    Pliki .pt to wagi PyTorch — OpenCV DNN ich nie wczyta. Konwersja w README." ;;
  esac

  # main.cpp:483 laduje na sztywno "yolov8n.onnx" sciezka wzgledna.
  # Jesli uzytkownik wskazal inny model, podstawiamy go tymczasowym symlinkiem
  # o oczekiwanej nazwie — dzieki temu kod pozostaje nietkniety.
  local target="$models_dir/$HARDCODED_MODEL" stash=""
  if [ "$MODEL" != "$HARDCODED_MODEL" ]; then
    # Jesli pod oczekiwana nazwa lezy prawdziwy plik, odsuwamy go na czas
    # uruchomienia i przywracamy przy wyjsciu — nic nie ginie.
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      stash="$target.talon-bak.$$"
      mv "$target" "$stash"
    fi
    ln -sfn "$MODEL" "$target"
    link_made=1
    info "Model: $MODEL (podstawiony jako $HARDCODED_MODEL)"
  else
    info "Model: $MODEL"
  fi

  # Sprzatanie niezaleznie od tego, jak program sie zakonczy (takze Ctrl-C).
  if [ "$link_made" = 1 ]; then
    # shellcheck disable=SC2064
    trap "rm -f '$target'; [ -n '$stash' ] && mv '$stash' '$target' 2>/dev/null; exit" EXIT INT TERM
  fi

  warn_code_only

  # Program laduje model sciezka wzgledna, wiec CWD musi byc katalogiem modeli.
  info "Start (CWD=$MODELS_DIR_NAME/, ESC konczy program)..."

  # Zmienne dla nadawania detekcji ustawiamy tylko wtedy, gdy uzytkownik je
  # podal — inaczej program bierze swoje wartosci domyslne.
  local -a env_args=()
  [ "$DETECTION_SOCKET_SET" = 1 ] && env_args+=("TALON_DETECTION_SOCKET=$DETECTION_SOCKET")
  [ -n "$ONLY_CLASS" ] && env_args+=("TALON_ONLY_CLASS=$ONLY_CLASS")
  [ -n "$SHARE_FRAMES" ] && env_args+=("TALON_SHARE_FRAMES=$SHARE_FRAMES")

  if [ ${#env_args[@]} -gt 0 ]; then
    ( cd "$models_dir" && env "${env_args[@]}" "$bin" )
  else
    ( cd "$models_dir" && "$bin" )
  fi
}

load_config

do_test() {
  local bin
  for c in "$BUILD_DIR/tests" "$BUILD_DIR/Release/tests" "$BUILD_DIR/Debug/tests"; do
    [ -x "$c" ] && { bin="$c"; break; }
  done
  [ -n "${bin:-}" ] || die "Nie znaleziono binarki testow. Uruchom: ./run.sh build"

  info "Testy jednostkowe..."
  "$bin"
}

case "${1:-run}" in
  build)   do_build ;;
  test)    do_build; do_test ;;
  clean)   info "Czyszczenie build/..."
           rm -rf "$BUILD_DIR"
           # usun wiszacy symlink do nieistniejacej juz bazy kompilacji
           [ -L "$ROOT/compile_commands.json" ] && rm -f "$ROOT/compile_commands.json"
           info "Gotowe." ;;
  rebuild) rm -rf "$BUILD_DIR"; do_build ;;
  run|"")  find_binary >/dev/null 2>&1 || do_build; do_run ;;
  -h|--help|help)
    sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *) die "Nieznana komenda: $1 (uzyj: build | run | test | clean | rebuild)" ;;
esac
