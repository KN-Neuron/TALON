// Wykrywanie przeszkod i obiektow dla drona (klasyczne CV, monokamera)
// Kompilacja:
//     ./run.sh            (CMake + build)
// Uruchomienie:
//     ./run.sh            (kamera 0)
//     ESC = wyjscie

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <memory>
#include <cmath>
#include <ctime>
#include <iostream>
#include <string>
#include <vector>

// Główne nagłówki OpenCV
#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>

// Moduly projektu
#include "Config.hpp"
#include "DetectionPublisher.hpp"
#include "FrameServer.hpp"
#include "KalmanFilter2D.hpp"
#include "OccupancyGrid2D.hpp"
#include "PerceptionMath.hpp"
#include "YoloDetector.hpp"

int main() {
  Config cfg;
  cv::VideoCapture cap(cfg.camIndex);
  if (!cap.isOpened()) {
    std::cerr << "Błąd otwarcia kamery!\n";
    return -1;
  }

  std::string modelPath = "yolov8n.onnx";
  YoloDetector detector(modelPath);

  cap.set(cv::CAP_PROP_FRAME_WIDTH, cfg.width);
  cap.set(cv::CAP_PROP_FRAME_HEIGHT, cfg.height);

  OccupancyGrid2D grid(0.1, 10.0); // 10cm/komórka, zasięg 10m

  // Nadawanie detekcji do klienta streamujacego. Sciezke gniazda mozna
  // nadpisac zmienna TALON_DETECTION_SOCKET; pusta wartosc wylacza nadawanie
  // (przydatne, gdy uruchamiamy sam podglad lokalny).
  const char *socket_env = std::getenv("TALON_DETECTION_SOCKET");
  const std::string socket_path =
      socket_env ? std::string(socket_env) : "/tmp/talon-detections.sock";
  DetectionPublisher publisher(socket_path);

  // Klasa do pokazania, zeby kadr nie tonal w setkach ramek z tla.
  // -1 = wszystkie klasy. Domyslnie 39 (butelka), jak przy testach.
  const char *class_env = std::getenv("TALON_ONLY_CLASS");
  const int only_class = class_env ? std::atoi(class_env) : 39;

  // Udostepnianie klatek innym procesom przez pamiec wspoldzielona. Ten modul
  // jest wlascicielem kamery — klient streamujacy nie otwiera jej sam, tylko
  // czyta stad. TALON_SHARE_FRAMES=0 wylacza.
  const char *share_env = std::getenv("TALON_SHARE_FRAMES");
  const bool share_frames = !(share_env && std::string(share_env) == "0");

  // Rozmiar rezerwujemy z gory, bo segment nie moze rosnac. Kamera moze zwrocic
  // inna rozdzielczosc niz zadana, wiec bierzemy zapas.
  const int shm_width = cfg.width;
  const int shm_height = cfg.height;

  std::unique_ptr<FrameServer> raw_frames;
  std::unique_ptr<FrameServer> annotated_frames;
  if (share_frames) {
    raw_frames =
        std::make_unique<FrameServer>("raw", shm_width, shm_height, 3);
    annotated_frames =
        std::make_unique<FrameServer>("annotated", shm_width, shm_height, 3);
  }
  uint64_t shared_frame_id = 0;

  // 1. GLOBALNY WEKTOR ŚLEDZONYCH OBIEKTÓW (Musi być POZA pętlą while!)
  std::vector<TrackedObject> tracked_objects;
  int next_unique_id = 1; // Licznik unikalnych ID (1, 2, 3...)

  cv::Mat frame;
  int64 tPrev = cv::getTickCount();
  CameraParams camera;

  camera.updateResolution(cfg.width, cfg.height);
  cv::namedWindow("Podglad Drona", cv::WINDOW_AUTOSIZE);
  while (true) {
    int64 tNow = cv::getTickCount();
    double dt = (tNow - tPrev) / cv::getTickFrequency();
    tPrev = tNow;

    cap >> frame;
    if (frame.empty())
      continue;

    ++shared_frame_id;

    // Surowa klatka idzie do odbiorcow zanim cokolwiek na niej narysujemy —
    // pozniej OpenCV modyfikuje `frame` w miejscu.
    if (raw_frames) {
      raw_frames->publish(frame, shared_frame_id);
    }

    std::string current_info_to_log = "";

    // A. DETEKCJA YOLO
    auto detections = detector.detect(frame);
    grid.clear();

    // B. PREDIKCJA FIZYKI DLA WSZYSTKICH ISTNIEJĄCYCH OBIEKTÓW
    for (auto &obj : tracked_objects) {
      obj.kalman.predict(dt);
      obj.time_since_update++; // Zwiększamy licznik klatek braku detekcji
    }

    // C. ASOCJACJA DANYCH I AKTUALIZACJA (Pętla po nowych detekcjach z YOLO)
    for (const auto &det : detections) {

      double w_real = getRealWidthForClass(det.class_id);
      // double h_real = getRealHeightForClass(det.class_id);

      double aspect_ratio = static_cast<double>(det.box.width) / det.box.height;
      if (aspect_ratio < 0.35) {
        w_real = 0.06;
      } else if (aspect_ratio >= 0.35) {
        w_real = 0.85;
      }

      double z_raw =
          PerceptionMath::calculateDepth(camera.fx, w_real, det.box.width);

      double u = det.box.x + (det.box.width / 2.0);
      double x_raw = PerceptionMath::calculateX(u, camera.cx, z_raw, camera.fx);

      // Szukamy najbliższego istniejącego obiektu (Najbliższy Sąsiad)
      int best_match_idx = -1;
      double min_dist = 999.0;

      for (size_t i = 0; i < tracked_objects.size(); ++i) {
        // Porównujemy tylko obiekty tej samej klasy!
        if (tracked_objects[i].class_id == det.class_id) {
          double pred_z = tracked_objects[i].kalman.getZ();
          double pred_x =
              PerceptionMath::calculateX(u, camera.cx, pred_z, camera.fx);

          // Euklidesowa odległość w przestrzeni 2D (X, Z)
          double dist = std::sqrt(std::pow(x_raw - pred_x, 2) +
                                  std::pow(z_raw - pred_z, 2));

          if (dist < min_dist) {
            min_dist = dist;
            best_match_idx = static_cast<int>(i);
          }
        }
      }

      // Progowanie: czy najbliższy obiekt jest dostatecznie blisko? (np.
      // < 1.0m)
      double MATCH_THRESHOLD = 1.0; // metry

      if (best_match_idx != -1 && min_dist < MATCH_THRESHOLD) {
        // [SCENARIUSZ 1]: ZNALEZIONO DOPASOWANIE -> Aktualizujemy istniejący
        // obiekt
        auto &obj = tracked_objects[best_match_idx];
        obj.kalman.update(z_raw);
        obj.time_since_update = 0; // Resetujemy licznik braku detekcji

        // Zapamietujemy detekcje przy sladzie — rendering i nadawanie
        // korzystaja z niej zamiast parowac wszystko po raz drugi.
        obj.last_box = det.box;
        obj.last_confidence = det.confidence;
        obj.last_lateral_m = x_raw;

      } else {
        // [SCENARIUSZ 2]: BRAK DOPASOWANIA -> Tworzymy nowy obiekt z własnym
        // Kalmanem!
        TrackedObject new_obj;
        new_obj.id = next_unique_id++;
        new_obj.class_id = det.class_id;
        new_obj.time_since_update = 0;
        new_obj.kalman.init(z_raw); // Inicjalizacja nowej instancji Kalmana
        new_obj.last_box = det.box;
        new_obj.last_confidence = det.confidence;
        new_obj.last_lateral_m = x_raw;

        tracked_objects.push_back(new_obj);
      }
    }

    // D. USUWANIE STARYCH OBIEKTÓW (Które zniknęły z kadru na dłużej niż 10
    // klatek)
    int MAX_LOST_FRAMES = 10;
    tracked_objects.erase(
        std::remove_if(tracked_objects.begin(), tracked_objects.end(),
                       [MAX_LOST_FRAMES](const TrackedObject &obj) {
                         return obj.time_since_update > MAX_LOST_FRAMES;
                       }),
        tracked_objects.end());

    // E. RENDEROWANIE, SIATKA BEV I ZEBRANIE RAMKI DO WYSLANIA
    //
    // Iterujemy po sladach, nie po detekcjach: slad ma juz przypisany swoj
    // box (faza C), wiec nie trzeba parowac obu list po raz drugi. Dzieki temu
    // obiekt chwilowo zgubiony przez YOLO nadal trafia do odbiorcy z
    // przewidywana pozycja i rosnacym frames_since_seen.
    std::vector<DetectionMessage> message_objects;
    message_objects.reserve(tracked_objects.size());

    for (const auto &obj : tracked_objects) {
      if (only_class >= 0 && obj.class_id != only_class) {
        continue;
      }
      // Slad bez ani jednej detekcji nie ma jeszcze sensownego boxa.
      if (obj.last_box.width <= 0 || obj.last_box.height <= 0) {
        continue;
      }

      const double z_filtered = obj.kalman.getZ();
      const double z_dot = obj.kalman.getZDot();
      const double ttc = PerceptionMath::calculateTTC(z_filtered, z_dot);

      const double u = obj.last_box.x + (obj.last_box.width / 2.0);
      const double x_pos =
          PerceptionMath::calculateX(u, camera.cx, z_filtered, camera.fx);

      // Na siatke BEV trafiaja tylko swieze obserwacje — przewidywania
      // zasmiecalyby mape.
      if (obj.time_since_update == 0) {
        grid.insertObstacle(x_pos, z_filtered);
      }

      const std::string className = getClassName(obj.class_id);

      // --- ramka do wyslania ---
      DetectionMessage message;
      message.track_id = obj.id;
      message.class_id = obj.class_id;
      message.class_name = className;
      message.confidence = obj.last_confidence;
      message.box = obj.last_box;
      message.has_position = true;
      message.lateral_m = x_pos;
      message.forward_m = z_filtered;
      // calculateTTC zwraca 999.0, gdy obiekt sie nie zbliza — wtedy pole jest
      // pomijane, zamiast wysylac wartosc-wartownika.
      message.has_ttc = (ttc < 999.0);
      message.closing_speed_mps = z_dot;
      message.time_to_collision_s = ttc;
      message.frames_since_seen = obj.time_since_update;
      message_objects.push_back(message);

      // --- podglad lokalny ---
      // Slad na przewidywaniu rysujemy na zolto, zeby bylo widac, ze YOLO go
      // chwilowo zgubilo.
      const bool fresh = (obj.time_since_update == 0);
      const cv::Scalar colour =
          fresh ? cv::Scalar(0, 255, 0) : cv::Scalar(0, 200, 255);

      const std::string info = cv::format(
          "ID %d: %s | Z: %.2fm | TTC: %.1fs | Size: %dx:%dpx", obj.id,
          className.c_str(), z_filtered, ttc, obj.last_box.width,
          obj.last_box.height);

      if (fresh) {
        current_info_to_log = info;
      }

      cv::rectangle(frame, obj.last_box, colour, 2);
      const int text_y = std::max(15, obj.last_box.y - 10);
      cv::putText(frame, info, cv::Point(obj.last_box.x, text_y),
                  cv::FONT_HERSHEY_SIMPLEX, 0.5, colour, 1);
    }

    // F. WYSLANIE RAMKI
    // Wysylamy takze pusta liste — odbiorca odroznia "nic nie widac" od
    // "producent przestal nadawac".
    publisher.publish(message_objects, frame.cols, frame.rows, dt);

    // Klatka z naniesionymi ramkami — dla odbiorcow, ktorzy chca gotowy
    // podglad zamiast rysowac nakladke po swojemu.
    if (annotated_frames) {
      annotated_frames->publish(frame, shared_frame_id);
    }

    // Wyświetlenie okien
    cv::Mat bevMat = grid.render();
    cv::imshow("Podglad Drona", frame);
    cv::imshow("Siatka Zajetosci (BEV)", bevMat);

    int key = cv::waitKey(1);

    if (key == 32) { // Klawisz SPACJA
      if (!current_info_to_log.empty()) {
        auto now = std::chrono::system_clock::now();
        std::time_t now_c = std::chrono::system_clock::to_time_t(now);
        struct tm *parts = std::localtime(&now_c);
        std::cout << "[LOG] " << current_info_to_log << std::endl;
      }

    } else if (key == 27) { // Klawisz ESC
      break;
    }
  }

  if (publisher.isOpen()) {
    std::cout << "[detekcje] Wyslano " << publisher.framesSent()
              << " klatek, pominieto " << publisher.framesDropped() << "\n";
  }
  if (raw_frames && raw_frames->isOpen()) {
    std::cout << "[klatki] Udostepniono " << raw_frames->framesPublished()
              << " klatek surowych, " 
              << (annotated_frames ? annotated_frames->framesPublished() : 0)
              << " z ramkami\n";
  }

  return 0;
}
