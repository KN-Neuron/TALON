// Wykrywanie przeszkod i obiektow dla drona (klasyczne CV, monokamera)
// Kompilacja:
//    g++ obstacle_detection.cpp -o detector `pkg-config --cflags --libs
//    opencv4`
// Uruchomienie:
//    ./detector            (kamera 0)
//    ESC = wyjscie

/*
 * ============================================================================
 * ŚCIĄGRAWKA MATEMATYCZNA - FILTR KALMANA (Notacja vs Kod C++)
 * ============================================================================
 *
 * [1. WEKTOR STANU]
 * x_hat (cv::Matx21d x_hat)
 *   -> Oznaczenie matematyczne: \hat{x} (lub x_k)
 *   -> Co to jest: Wektor stanu układu (nasza najlepsza estymata).
 *   -> W naszym kodzie (2x1):
 *        x_hat(0, 0) = Z      -> Szacowana odległość do przeszkody [metry]
 *        x_hat(1, 0) = \dot{Z} -> Szacowana prędkość zbliżania [m/s]
 *
 * [2. NIEPEWNOŚĆ / KOWARIANCJA]
 * P (cv::Matx22d P)
 *   -> Oznaczenie matematyczne: P_k (Error Covariance Matrix)
 *   -> Co to jest: Macierz kowariancji błędu estymacji (rozmiar 2x2).
 *   -> Jak ją czytać:
 *        P(0,0) -> Wariancja błędu pozycji Z (jak bardzo "pływa" odległość)
 *        P(1,1) -> Wariancja błędu prędkości \dot{Z}
 *        P(0,1) / P(1,0) -> Kowariancja (zależność błędu pozycji i prędkości)
 *
 * [3. MACIERZ PRZEJŚCIA FIZYKI]
 * Phi (cv::Matx22d Phi)
 *   -> Oznaczenie matematyczne: \mathbf{\Phi} (State Transition Matrix)
 *   -> Co to jest: Macierz fizyki Newtona przemieszczająca stan o czas dt.
 *   -> Postać (2x2):
 *        [ 1,  dt ]  -> Nowa pozycja = stara pozycja + prędkość * dt
 *        [ 0,   1 ]  -> Nowa prędkość = stara prędkość (model stałej prędkości)
 *
 * [4. SZUM PROCESU (FIZYKI)]
 * Q (cv::Matx22d Q)
 *   -> Oznaczenie matematyczne: Q_k (Process Noise Covariance)
 *   -> Co to jest: Macierz kowariancji szumu modelu fizycznego.
 *   -> Znaczenie: Mówi, jak bardzo nie ufamy czystej fizyce (np. nagły wiatr,
 * drgania drona).
 *
 * [5. MACIERZ OBSERWACJI (POMIARU)]
 * H (cv::Matx12d H)
 *   -> Oznaczenie matematyczne: H_k (Measurement Matrix)
 *   -> Co to jest: Macierz łącząca stan (2 elementy) z pomiarem z kamery (1
 * element).
 *   -> Postać (1x2): [1.0, 0.0] -> Mierzymy wprost odległość Z, ale NIE
 * mierzymy prędkości.
 *
 * [6. SZUM POMIARU (KAMERY)]
 * R (double R)
 *   -> Oznaczenie matematyczne: R_k (Measurement Noise Variance)
 *   -> Co to jest: Wariancja szumu kamery.
 *   -> Znaczenie: Mówi, jak mocno trzęsie się/szumi Bounding Box na klatce
 * obrazu z OpenCV.
 *
 * [7. WZMOCNIENIE KALMANA]
 * K (cv::Matx21d K)
 *   -> Oznaczenie matematyczne: K_k (Kalman Gain)
 *   -> Co to jest: Waga (wektor 2x1) określająca, czy bardziej wierzyć fizyce,
 * czy kamerze.
 *   -> Obliczenie: K = P * H^T * (H * P * H^T + R)^-1
 *
 * [8. INNOWACJA (BŁĄD POMIARU)]
 * y (double y)
 *   -> Oznaczenie matematyczne: y_k lub r_k (Innovation / Residual)
 *   -> Co to jest: Różnica między tym, co zmierzyła kamera, a tym, co
 * przewidział model.
 *   -> Wzór: y = z_meas - (H * x_hat)
 * ============================================================================
 */

#include <iostream>
#include <opencv2/dnn.hpp>
#include <opencv2/opencv.hpp>
#include <string>
#include <vector>

#include <cmath>
#include <iostream>
#include <opencv2/imgproc.hpp>
#include <opencv2/opencv.hpp>
#include <vector>

// ============================================================================
// DETEKTOR YOLO (OpenCV DNN)
// ============================================================================

// Struktura na wynik detekcji
struct Detection {
  int class_id;
  float confidence;
  cv::Rect box;
};

class YoloDetector {
private:
  cv::dnn::Net net;
  const cv::Size input_size = cv::Size(640, 640);
  float conf_threshold = 0.45f;
  float nms_threshold = 0.45f;

public:
  YoloDetector(const std::string &model_path) {
    // Wczytanie modelu ONNX przez silnik OpenCV DNN
    net = cv::dnn::readNetFromONNX(model_path);

    // Jeśli masz GPU/CUDA na laptopie, możesz odblokować poniższe 2 linie:
    // net.setPreferableBackend(cv::dnn::DNN_BACKEND_CUDA);
    // net.setPreferableTarget(cv::dnn::DNN_TARGET_CUDA);
    net.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);
    net.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);
  }

  std::vector<Detection> detect(const cv::Mat &frame) {
    std::vector<Detection> detections;
    if (frame.empty())
      return detections;

    // 1. Pre-processing: Skalowanie do 640x640, zmiana BGR->RGB, normalizacja
    // [0, 1]
    cv::Mat blob;
    cv::dnn::blobFromImage(frame, blob, 1.0 / 255.0, input_size, cv::Scalar(),
                           true, false);
    net.setInput(blob);

    // 2. Inferencja (Forward Pass)
    cv::Mat output;
    net.forward(output);

    // Wyjście YOLOv8/v11 z OpenCV ma zazwyczaj postać [1, 84, 8400]
    // 84 = [x_center, y_center, w, h] + 80 klas COCO
    // 8400 = liczba predykcji propozycji ramek

    // Transpozycja z [1, 84, 8400] na [8400, 84] dla wygody iteracji
    cv::Mat outputs = output.reshape(1, output.size[1]).t(); // [8400, 84]

    float x_factor = static_cast<float>(frame.cols) / input_size.width;
    float y_factor = static_cast<float>(frame.rows) / input_size.height;

    std::vector<int> class_ids;
    std::vector<float> confidences;
    std::vector<cv::Rect> boxes;

    // 3. Post-processing: Przeglądanie 8400 propozycji ramek
    for (int i = 0; i < outputs.rows; ++i) {
      // Przetwarzamy wiersz odpowiadający 1 propozycji
      const float *row = outputs.ptr<float>(i);

      // Wskaźnik do prawdopodobieństw 80 klas (zaczynają się od indeksu 4)
      const float *scores = row + 4;

      cv::Point class_id_point;
      double max_score;
      cv::minMaxLoc(cv::Mat(1, 80, CV_32F, const_cast<float *>(scores)),
                    nullptr, &max_score, nullptr, &class_id_point);

      if (max_score >= conf_threshold) {
        float cx = row[0] * x_factor;
        float cy = row[1] * y_factor;
        float w = row[2] * x_factor;
        float h = row[3] * y_factor;

        int left = static_cast<int>(cx - w / 2.0f);
        int top = static_cast<int>(cy - h / 2.0f);

        class_ids.push_back(class_id_point.x);
        confidences.push_back(static_cast<float>(max_score));
        boxes.push_back(
            cv::Rect(left, top, static_cast<int>(w), static_cast<int>(h)));
      }
    }

    // 4. Non-Maximum Suppression (NMS) - odrzucanie nakładających się ramek
    std::vector<int> indices;
    cv::dnn::NMSBoxes(boxes, confidences, conf_threshold, nms_threshold,
                      indices);

    for (int idx : indices) {
      detections.push_back({class_ids[idx], confidences[idx], boxes[idx]});
    }

    return detections;
  }
};

// ============================================================================
// 1. FILTR KALMANA 2D (Odległość Z + Prędkość Z_dot)
// ============================================================================
class KalmanFilter2D {
private:
  cv::Matx21d x_hat; // Wektor stanu [Z, Z_dot]^T
  cv::Matx22d P;     // Kowariancja błędu
  cv::Matx22d Q;     // Szum procesu (fizyki)
  cv::Matx12d H;     // Macierz obserwacji [1, 0]
  double R;          // Szum pomiarowy kamery

  bool initialized;

public:
  KalmanFilter2D() : initialized(false) {
    x_hat = cv::Matx21d(0.0, 0.0);

    // Początkowa niepewność
    P = cv::Matx22d(0.7, 0.0, 0.0, 2.0);

    // Szum procesu (Q) - jak bardzo ufasz niespodziewanym ruchom
    Q = cv::Matx22d(0.05, 0.0, 0.0, 0.1);

    // Obserwacja: mierzymy tylko Z, nie mierzymy bezpośrednio prędkości.
    // Filtr Kalmana estymuje prędkość na podstawie różnic pozycji w czasie.
    // To odpowiednik wyliczania aproksymowanej pochodnej: Ż_new ~= Ż_old + K_ż
    // * (z_raw - Z_pred)
    H = cv::Matx12d(1.0, 0.0);

    // Szum pomiaru (R) - wariancja błędu detekcji b-boxa
    R = 1.5;
  }

  void init(double initial_z) {
    x_hat(0, 0) = initial_z;
    x_hat(1, 0) = 0.0; // Prędkość początkowa = 0
    initialized = true;
  }

  bool isInitialized() const { return initialized; }

  // Faza 1: Project (Fizyka drona)
  void predict(double dt) {
    if (!initialized)
      return;

    // Macierz przejścia Phi z czasem dt.
    // Wynika bezpośrednio z fizyki dynamiki Newtona dla ruchu jednostajnego
    // przy założeniu, że w przedziale czasu dt prędkość jest stała.
    cv::Matx22d Phi(1.0, dt, 0.0, 1.0);

    // Obliczenie Z_{k+1} z Kalmana: x'_{k+1} = Phi * x_k
    x_hat = Phi * x_hat;

    // Aktualizacja niepewności procesu: P'_{k+1} = Phi * P_k * Phi^T + Q
    P = Phi * P * Phi.t() + Q;
  }

  // Faza 2: Update (Korekta z kamery)
  void update(double z_meas) {
    if (!initialized) {
      init(z_meas);
      return;
    }

    // K_k = P' * H^T * (H * P' * H^T + R)^-1
    cv::Matx21d HT = H.t();
    double S = (H * P * HT)(0, 0) + R;
    cv::Matx21d K = (P * HT) * (1.0 / S);

    // Innowacja (błąd pomiaru): y = z - H * x'
    double y = z_meas - (H * x_hat)(0, 0);

    // Nowy stan: x_k = x'_k + K * y
    x_hat = x_hat + K * y;

    // Kowariancja: P_k = (I - K * H) * P'
    cv::Matx22d I = cv::Matx22d::eye();
    P = (I - K * H) * P;
  }

  double getZ() const { return x_hat(0, 0); }
  double getZDot() const { return x_hat(1, 0); }
};

// ============================================================================
// 2. GEOMETRIA 3D I SIATKA ZAJĘTOŚCI (BEV)
// ============================================================================
class OccupancyGrid2D {
private:
  static constexpr int GRID_SIZE = 100; // 100x100 komórek
  double cell_size;                     // 0.1m (10cm) na komórkę
  double max_range;                     // max 10 metrów przed dronem
  int grid[GRID_SIZE][GRID_SIZE];

public:
  OccupancyGrid2D(double cellSize = 0.1, double maxRange = 10.0)
      : cell_size(cellSize), max_range(maxRange) {
    clear();
  }

  void clear() { std::memset(grid, 0, sizeof(grid)); }

  // Rzutowanie punktu (X, Z) na siatkę BEV
  void insertObstacle(double X, double Z) {
    if (Z <= 0.0 || Z >= max_range)
      return;

    // Mapowanie: X od [-max_range/2, max_range/2] na [0, GRID_SIZE]
    int grid_x = static_cast<int>((X + (max_range / 2.0)) / cell_size);
    int grid_z = static_cast<int>(Z / cell_size);

    if (grid_x >= 0 && grid_x < GRID_SIZE && grid_z >= 0 &&
        grid_z < GRID_SIZE) {
      grid[grid_z][grid_x] = 1; // Oznaczenie komórki jako zajętej
    }
  }

  // Wizualizacja siatki BEV w małym oknie OpenCV
  cv::Mat render() const {
    cv::Mat vis = cv::Mat::zeros(GRID_SIZE * 2, GRID_SIZE * 2, CV_8UC3);
    for (int z = 0; z < GRID_SIZE; ++z) {
      for (int x = 0; x < GRID_SIZE; ++x) {
        if (grid[z][x] > 0) {
          cv::rectangle(vis, cv::Rect(x * 2, (GRID_SIZE - 1 - z) * 2, 2, 2),
                        cv::Scalar(0, 0, 255), -1);
        }
      }
    }
    // Pozycja drona (na dole, w środku)
    cv::circle(vis, cv::Point(GRID_SIZE, GRID_SIZE * 2 - 5), 3,
               cv::Scalar(0, 255, 0), -1);
    return vis;
  }
};

// Moduł przeliczania czysto geometrycznego
namespace PerceptionMath {
// Model kamery otworkowej Z = (f_x * W) / w
inline double calculateDepth(double fx, double realWidth, double bboxWidth) {
  if (bboxWidth <= 0)
    return 0.0;
  return (fx * realWidth) / bboxWidth;
}

// Współrzędna poprzeczna X = ((u - cx) * Z) / fx
// Odwracamy rzutowanie 3D do 2D, czyli przechodzimy z pikseli obrazu na metry w
// świecie rzeczywistym. u to środek bounding boxa na ekranie (np. u = 450px) cx
// to środek optyczny macierzy kamery (zazwyczaj połowa szerokości kadru, np.
// 640x480 -> 320px) u - cx to odległość przeszkody od środka kadru w pikselach:
//   - jeśli u = 320 (środek), to u - cx = 0 => X = 0 (obiekt leci wprost na
//   drona)
//   - jeśli obiekt jest z prawej (u = 500), to u - cx = 180px => X > 0 (obiekt
//   po prawej)
// (Współrzędna w metrach X / głębia w metrach Z) = (odchylenie w pikselach (u -
// c_x)) / ogniskowa w pikselach. Przekształcenie tego wzoru daje funkcję
// poniżej:
inline double calculateX(double u, double cx, double Z, double fx) {
  return ((u - cx) * Z) / fx;
}

// Czas do kolizji (TTC)
inline double calculateTTC(double Z, double Z_dot) {
  if (Z_dot >= -0.01)
    return 999.0; // Przeszkoda się nie zbliża
  return -(Z / Z_dot);
}
} // namespace PerceptionMath

// ============================================================================
// 3. PĘTLA GŁÓWNA SYSTEMU
// ============================================================================
// Ogólnie tu trzeba będzie dodać jakąś kalibrację na starcie, np. plik z
// configiem, a potem jednorazowa konfiguracja. Ew. bawić się z jednorazową
// kalibracją typu: user pokazuje kartkę A4 do kamery z odległości 1.0m i kod
// odwraca wzór: f_x = (Z_znane * w) / W_znane

struct CameraParams {
  double h_fov_deg = 65.0; // Domyślny kąt widzenia większości webcamów/dronów
  double fx = 500.0;
  double cx = 320.0;

  void updateResolution(int imgWidth, int imgHeight) {
    cx = imgWidth / 2.0;

    // Przeliczenie fx dynamicznie przy zmianie rozdzielczości (np. z 640x480 na
    // 1280x720)
    double fov_rad = h_fov_deg * (M_PI / 180.0);
    fx = imgWidth / (2.0 * std::tan(fov_rad / 2.0));
  }
};

struct Config {
  int camIndex = 0;
  int width = 640;
  int height = 480;
  double minArea = 700.0;
  double fx = 500.0;      // Ogniskowa kamery w px (przykładowa kalibracja)
  double cx = 320.0;      // Środek optyczny (width / 2)
  double realWidth = 0.5; // Szacowana szerokość przeszkody w metrach (50 cm)
};

// Ogniskowa reprezentuje stosunek fizycznej ogniskowej soczewki f do fizycznego
// rozmiaru pojedynczego piksela matrycy d_x: f_x = f / d_x.
// Macierz kalibracji K:
//   [f_x  0   c_x]
//   [ 0  f_y  c_y]
//   [ 0   0    1 ]
// c_x, c_y to optyczny środek matrycy.
// f_x, f_y to ogniskowe w osi X i Y wyrażone w pikselach.
//
// Aby nie podawać ogniskowej w milimetrach (f), bierzemy ogniskową pikselową:
// f_x = W_img / (2 * tan(FOV_x / 2))
// gdzie FOV_x to kąt widzenia (np. 65 stopni).

int main() {
  Config cfg;
  cv::VideoCapture cap(cfg.camIndex);
  if (!cap.isOpened()) {
    std::cerr << "Błąd otwarcia kamery!\n";
    return -1;
  }

  cap.set(cv::CAP_PROP_FRAME_WIDTH, cfg.width);
  cap.set(cv::CAP_PROP_FRAME_HEIGHT, cfg.height);

  KalmanFilter2D kalman;
  OccupancyGrid2D grid(0.1, 10.0); // 10cm/komórka, zasięg 10m

  cv::Mat frame, gray, edges;
  std::vector<std::vector<cv::Point>> contours;

  int64 tPrev = cv::getTickCount();

  while (true) {
    // Obliczenie czystego delta_t dla Filtra Kalmana
    int64 tNow = cv::getTickCount();
    double dt = (tNow - tPrev) / cv::getTickFrequency();
    tPrev = tNow;

    cap >> frame;
    if (frame.empty())
      continue;

    // 1. Predykcja fizyki w Kalmanie (Project)
    kalman.predict(dt);
    grid.clear();

    // Wstępny pre-processing obrazu
    cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY);
    cv::GaussianBlur(gray, gray, cv::Size(3, 3), 0);
    cv::Canny(gray, edges, 50, 150);
    cv::findContours(edges, contours, cv::RETR_EXTERNAL,
                     cv::CHAIN_APPROX_SIMPLE);

    double minDistanceInFrame = 999.0;
    bool detectedAny = false;

    for (const auto &c : contours) {
      if (cv::contourArea(c) < cfg.minArea)
        continue;

      cv::Rect box = cv::boundingRect(c);

      if (box.height == 0)
        continue;

      double aspectRatio = static_cast<double>(box.width) / box.height;

      double minAR = 0.5;
      double maxAR = 1.2;
      if (aspectRatio < minAR || aspectRatio > maxAR) {
        continue;
      }

      detectedAny = true;

      // 2. Pomiar z kamery (model otworkowy)
      double z_raw =
          PerceptionMath::calculateDepth(cfg.fx, cfg.realWidth, box.width);

      // 3. Update stanu w Kalmanie
      kalman.update(z_raw);

      double z_filtered = kalman.getZ();
      double z_dot = kalman.getZDot();
      double ttc = PerceptionMath::calculateTTC(z_filtered, z_dot);

      // Wyznaczenie pozycji X w układzie BEV
      double u = box.x + (box.width / 2.0);
      double x_pos = PerceptionMath::calculateX(u, cfg.cx, z_filtered, cfg.fx);

      if (z_filtered < minDistanceInFrame) {
        minDistanceInFrame = z_filtered;
      }

      // Naniesienie przeszkody na siatkę zajętości
      grid.insertObstacle(x_pos, z_filtered);

      // Wizualizacja na obrazie
      cv::rectangle(frame, box, cv::Scalar(0, 255, 0), 2);
      std::string info = cv::format("Z: %.2fm | TTC: %.1fs", z_filtered, ttc);
      cv::putText(frame, info, cv::Point(box.x, box.y - 10),
                  cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
    }

    // Renderowanie podglądu siatki BEV
    cv::Mat bevMat = grid.render();
    cv::imshow("Podglad Drona", frame);
    cv::imshow("Siatka Zajetosci (BEV)", bevMat);

    if (cv::waitKey(1) == 27)
      break; // ESC
  }

  return 0;
}
int main_yolo() {
  std::string modelPath = "yolov8n.onnx";

  YoloDetector detector(modelPath);

  cv::VideoCapture cap(0); // Otwarcie kamery 0
  if (!cap.isOpened()) {
    std::cerr << "Błąd otwarcia kamery!\n";
    return -1;
  }

  cv::Mat frame;
  while (true) {
    cap >> frame;
    if (frame.empty())
      break;

    // Wywołanie detekcji
    auto detections = detector.detect(frame);

    // Rysowanie wyników na ekranie
    for (const auto &det : detections) {
      cv::rectangle(frame, det.box, cv::Scalar(0, 255, 0), 2);
      std::string label =
          cv::format("Class %d: %.2f", det.class_id, det.confidence);
      cv::putText(frame, label, cv::Point(det.box.x, det.box.y - 5),
                  cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
    }

    cv::imshow("YOLO OpenCV C++ Test", frame);
    if (cv::waitKey(1) == 27)
      break; // ESC
  }

  return 0;
}
