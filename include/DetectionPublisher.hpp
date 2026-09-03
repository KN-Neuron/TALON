#pragma once

#include <string>
#include <vector>

#include <opencv2/core.hpp>

// ============================================================================
// NADAWANIE DETEKCJI DO KLIENTA STREAMUJACEGO
// ============================================================================
//
// Jedna klatka = jeden datagram JSON wyslany na gniazdo uniksowe. Klient
// (apps/client) czyta je i przekazuje dalej kanalem danych WebRTC, a
// przegladarka rysuje ramki na obrazie.
//
// Format opisuje docs/detection-protocol.md — jest wspolny dla wszystkich
// trzech jezykow w projekcie, wiec zmiana nazwy pola wymaga zmiany takze tam.
//
// SOCK_DGRAM daje granice wiadomosci za darmo: jedno sendto() to jedna ramka,
// wiec nie trzeba doklejac dlugosci. Gdy odbiorca nie nadaza, jadro gubi
// datagramy — i o to chodzi, bo nieaktualna detekcja jest bezwartosciowa.
//
// Nadawanie jest nieblokujace: jesli bufor gniazda jest pelny, ramka przepada
// zamiast wstrzymywac petle detekcji. Percepcja nigdy nie czeka na podglad.

// Pojedynczy obiekt w wysylanej ramce.
//
// Pola opcjonalne (position, closing_speed_mps, time_to_collision_s) sa
// pomijane w JSON-ie, gdy `has_position` / `has_ttc` sa falszywe — odbiorca
// musi sobie radzic z ich brakiem.
struct DetectionMessage {
  int track_id = 0;
  int class_id = 0;
  std::string class_name;
  double confidence = 0.0;

  cv::Rect box;

  bool has_position = false;
  double lateral_m = 0.0; // ujemne = na lewo od srodka kadru
  double forward_m = 0.0; // odleglosc przed dronem

  bool has_ttc = false;
  double closing_speed_mps = 0.0; // ujemne = obiekt sie zbliza
  double time_to_collision_s = 0.0;

  int frames_since_seen = 0;
};

class DetectionPublisher {
public:
  // Otwiera gniazdo. Nie rzuca wyjatkiem, gdy sie nie uda — brak podgladu nie
  // moze zatrzymac detekcji; isOpen() mowi, czy nadawanie dziala.
  explicit DetectionPublisher(const std::string &socket_path);
  ~DetectionPublisher();

  // Kopiowanie zabronione: obiekt jest wlascicielem deskryptora.
  DetectionPublisher(const DetectionPublisher &) = delete;
  DetectionPublisher &operator=(const DetectionPublisher &) = delete;

  bool isOpen() const { return fd_ >= 0; }

  // Wysyla jedna klatke. Zwraca false, gdy datagram przepadl (brak odbiorcy,
  // pelny bufor) — wywolujacy moze to zignorowac.
  bool publish(const std::vector<DetectionMessage> &objects, int image_width,
               int image_height, double frame_interval_s);

  // Statystyki do logowania.
  long framesSent() const { return frames_sent_; }
  long framesDropped() const { return frames_dropped_; }

private:
  std::string buildJson(const std::vector<DetectionMessage> &objects,
                        int image_width, int image_height,
                        double frame_interval_s) const;

  int fd_ = -1;
  std::string socket_path_;

  mutable long frame_id_ = 0;
  long frames_sent_ = 0;
  long frames_dropped_ = 0;

  // Zeby nie zasypywac konsoli, gdy klient nie jest uruchomiony.
  bool warned_no_listener_ = false;
};
