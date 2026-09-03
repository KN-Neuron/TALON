#pragma once

#include <cstdint>
#include <string>

#include <opencv2/core.hpp>

// ============================================================================
// UDOSTEPNIANIE KLATEK PRZEZ PAMIEC WSPOLDZIELONA
// ============================================================================
//
// Ten modul jest wlascicielem kamery. Inne procesy nie otwieraja jej sami —
// podlaczaja sie tutaj i czytaja gotowe klatki.
//
// Dwa strumienie, wybierane przez odbiorce przy podlaczeniu:
//   "raw"       — czysty obraz z kamery
//   "annotated" — ten sam obraz z naniesionymi ramkami i etykietami
//
// Dlaczego pamiec wspoldzielona, a nie gniazdo: klatka 640x480 BGR to ~920 KB,
// przy 30 fps daje 27 MB/s. Przez gniazdo kazdy bajt przeszedlby przez jadro
// dwa razy; tutaj czytelnik siega wprost do tych samych stron pamieci, wiec
// koszt jest bliski zeru. Cena: oba procesy musza byc na tym samym urzadzeniu.
//
// --- Jak dziala synchronizacja ---
//
// Bufor cykliczny na kilka klatek. Kazdy slot ma licznik `sequence`:
//   nieparzysty = zapis w toku, parzysty = klatka kompletna.
//
// Czytelnik: zapamietuje sequence, kopiuje dane, sprawdza sequence ponownie.
// Jesli sie zmienil albo byl nieparzysty — pisarz nadpisal slot w trakcie
// czytania, wiec kopia jest podejrzana i czytelnik ja odrzuca.
//
// Dzieki temu nie ma zadnych blokad: pisarz nigdy nie czeka na czytelnika,
// a wolny czytelnik gubi klatki zamiast spowalniac detekcje. Dla podgladu na
// zywo to wlasciwy kompromis — nieaktualna klatka jest bezwartosciowa.

namespace frameshm {

// Zmieniamy przy kazdej modyfikacji ukladu pamieci. Czytelnik z inna wersja
// odmawia podlaczenia, zamiast interpretowac bajty po swojemu.
constexpr uint32_t kLayoutVersion = 1;

// Tyle klatek trzymamy w buforze. Wiecej = czytelnik ma wieksze okno na
// dokonczenie kopii, zanim pisarz wroci do tego samego slotu.
constexpr int kSlotCount = 4;

constexpr uint32_t kMagic = 0x544C4E46; // "TLNF"

// Naglowek pojedynczego slotu.
struct SlotHeader {
  // Nieparzysty = zapis w toku. Zwiekszany dwa razy na klatke.
  uint32_t sequence;
  uint32_t width;
  uint32_t height;
  uint32_t channels;
  uint64_t frame_id;
  int64_t timestamp_ms;
  uint32_t data_bytes;
  uint32_t reserved;
};

// Naglowek calego segmentu, na jego poczatku.
struct SegmentHeader {
  uint32_t magic;
  uint32_t layout_version;
  uint32_t slot_count;
  uint32_t slot_stride; // odleglosc miedzy slotami w bajtach
  uint32_t max_width;
  uint32_t max_height;
  uint32_t max_channels;
  // Ostatni slot zapisany w calosci. Czytelnik zaczyna od niego.
  uint32_t latest_slot;
};

// Nazwa segmentu dla danego strumienia, np. "/talon.raw".
std::string segmentName(const std::string &stream_name);

} // namespace frameshm

// ============================================================================

// Publikuje klatki jednego strumienia.
//
// Nie rzuca wyjatkiem, gdy segmentu nie da sie utworzyc — brak podgladu nie
// moze zatrzymac detekcji. isOpen() mowi, czy publikowanie dziala.
class FrameServer {
public:
  // `stream_name` to czlon nazwy segmentu ("raw", "annotated").
  // Rozmiar rezerwujemy z gory, bo segment nie moze rosnac po utworzeniu.
  FrameServer(const std::string &stream_name, int max_width, int max_height,
              int channels = 3);
  ~FrameServer();

  FrameServer(const FrameServer &) = delete;
  FrameServer &operator=(const FrameServer &) = delete;

  bool isOpen() const { return mapping_ != nullptr; }

  // Kopiuje klatke do nastepnego slotu. Klatka wieksza niz zarezerwowany
  // rozmiar jest odrzucana (zwraca false) — nie chcemy pisac poza segment.
  bool publish(const cv::Mat &frame, uint64_t frame_id);

  long framesPublished() const { return frames_published_; }
  const std::string &name() const { return segment_name_; }

private:
  std::string segment_name_;
  int fd_ = -1;
  void *mapping_ = nullptr;
  size_t mapping_bytes_ = 0;

  int max_width_;
  int max_height_;
  int channels_;
  size_t slot_stride_ = 0;

  int next_slot_ = 0;
  long frames_published_ = 0;
};
