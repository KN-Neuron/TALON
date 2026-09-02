// Wykrywanie przeszkod i obiektow dla drona (klasyczne CV, monokamera)
// Kompilacja:
//     ./run.sh            (CMake + build)
// Uruchomienie:
//     ./run.sh            (kamera 0)
//     ESC = wyjscie

#include <algorithm>
#include <chrono>
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

      } else {
        // [SCENARIUSZ 2]: BRAK DOPASOWANIA -> Tworzymy nowy obiekt z własnym
        // Kalmanem!
        TrackedObject new_obj;
        new_obj.id = next_unique_id++;
        new_obj.class_id = det.class_id;
        new_obj.time_since_update = 0;
        new_obj.kalman.init(z_raw); // Inicjalizacja nowej instancji Kalmana

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

    // E. RENDEROWANIE I WIZUALIZACJA DLA WSZYSTKICH AKTYWNYCH OBIEKTÓW
    for (const auto &det : detections) {
      // Znajdujemy przypisany obiekt do narysowania
      for (const auto &obj : tracked_objects) {
        // dałem klase 39 bo chce mieć tylko butelki zamiast setek green boxów w
        // tle
        if (obj.class_id == det.class_id && obj.time_since_update == 0 &&
            obj.class_id == 39) {
          double z_filtered = obj.kalman.getZ();
          double z_dot = obj.kalman.getZDot();
          double ttc = PerceptionMath::calculateTTC(z_filtered, z_dot);

          double u = det.box.x + (det.box.width / 2.0);
          double x_pos =
              PerceptionMath::calculateX(u, camera.cx, z_filtered, camera.fx);

          // Nanosimy na siatkę BEV
          grid.insertObstacle(x_pos, z_filtered);

          // Rysowanie informacji na ekranie BGR
          std::string className = getClassName(obj.class_id);
          auto box_width = det.box.width;
          auto box_heigth = det.box.height;
          std::string info = cv::format(
              "ID %d: %s | Z: %.2fm | TTC: %.1fs | Size: %dx:%dpx", obj.id,
              className.c_str(), z_filtered, ttc, box_width, box_heigth);

          current_info_to_log = info;

          cv::rectangle(frame, det.box, cv::Scalar(0, 255, 0), 2);
          int text_y = std::max(15, det.box.y - 10);
          cv::putText(frame, info, cv::Point(det.box.x, text_y),
                      cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
        }
      }
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

  return 0;
}
