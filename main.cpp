// Wykrywanie przeszkod i obiektow dla drona (klasyczne CV, monokamera)
// Kompilacja:
//     g++ obstacle_detection.cpp -o detector `pkg-config --cflags --libs
//     opencv4`
// Uruchomienie:
//     ./detector            (kamera 0)
//     ESC = wyjscie

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

#include <cmath>
#include <cstring>
#include <iostream>
#include <iterator>
#include <opencv2/highgui.hpp>
#include <string>
#include <vector>

// Główne nagłówki OpenCV
#include <opencv2/dnn.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/opencv.hpp>
// ============================================================================
// DETEKTOR YOLO (OpenCV DNN)
// ============================================================================

const std::vector<std::string> COCO_CLASSES = {
    "person",        "bicycle",      "car",
    "motorcycle",    "airplane",     "bus",
    "train",         "truck",        "boat",
    "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench",        "bird",
    "cat",           "dog",          "horse",
    "sheep",         "cow",          "elephant",
    "bear",          "zebra",        "giraffe",
    "backpack",      "umbrella",     "handbag",
    "tie",           "suitcase",     "frisbee",
    "skis",          "snowboard",    "sports ball",
    "kite",          "baseball bat", "baseball glove",
    "skateboard",    "surfboard",    "tennis racket",
    "bottle",        "wine glass",   "cup",
    "fork",          "knife",        "spoon",
    "bowl",          "banana",       "apple",
    "sandwich",      "orange",       "broccoli",
    "carrot",        "hot dog",      "pizza",
    "donut",         "cake",         "chair",
    "couch",         "potted plant", "bed",
    "dining table",  "toilet",       "tv",
    "laptop",        "mouse",        "remote",
    "keyboard",      "cell phone",   "microwave",
    "oven",          "toaster",      "sink",
    "refrigerator",  "book",         "clock",
    "vase",          "scissors",     "teddy bear",
    "hair drier",    "toothbrush"};

std::string getClassName(int class_id) {
  if (class_id >= 0 && class_id < static_cast<int>(COCO_CLASSES.size())) {
    return COCO_CLASSES[class_id];
  }
  return "unknown";
}

double getRealWidthForClass(int class_id) {
  switch (class_id) {
  case 0:
    return 0.45; // 'person' (jeśli Bounding Box łapie tylko głowę/twarz) ->
                 // ok.
                 // 20 cm
  // case 0: return 0.45; // 'person' (jeśli Bounding Box łapie całe popiersie z
  // ramionami) -> ok. 45 cm
  case 39:
    return 0.07;
  case 66:
    return 0.15; // 'remote' / małe przedmioty
  case 73:
    return 0.25; // 'clock' (zegar na ścianie) -> np. 25 cm
  default:
    return 0.30;
  }
}
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
  cv::Matx22d P;
  // Kowariancja błędu
  cv::Matx22d Q;
  // Szum procesu (fizyki)
  cv::Matx12d H;
  // Macierz obserwacji [1, 0]
  double R;
  // Szum pomiarowy kamery

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

struct TrackedObject {
  int id;
  int class_id;
  KalmanFilter2D kalman;
  int time_since_update;
};

// ============================================================================
// 2. GEOMETRIA 3D I SIATKA ZAJĘTOŚCI (BEV)
// ============================================================================
class OccupancyGrid2D {
private:
  static constexpr int GRID_SIZE = 100; // 100x100 komórek
  double cell_size;
  // 0.1m (10cm) na komórkę
  double max_range;
  // max 10 metrów przed dronem
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
//    - jeśli u = 320 (środek), to u - cx = 0 => X = 0 (obiekt leci wprost na
//    drona)
//    - jeśli obiekt jest z prawej (u = 500), to u - cx = 180px => X > 0 (obiekt
//    po prawej)
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
  double h_fov_deg = 60.0; // Domyślny kąt widzenia większości webcamów/dronów
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
  double fx = 500.0;
  // Ogniskowa kamery w px (przykładowa kalibracja)
  double cx = 320.0;
  // Środek optyczny (width / 2)
  double realWidth = 0.5; // Szacowana szerokość przeszkody w metrach (50 cm)
};

// Ogniskowa reprezentuje stosunek fizycznej ogniskowej soczewki f do fizycznego
// rozmiaru pojedynczego piksela matrycy d_x: f_x = f / d_x.
// Macierz kalibracji K:
//    [f_x  0   c_x]
//    [ 0  f_y  c_y]
//    [ 0   0    1 ]
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
          cv::putText(frame, info, cv::Point(det.box.x, det.box.y - 10),
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
        std::cout << "[LOG] " << current_info_to_log << std::endl;
      }

    } else if (key == 27) { // Klawisz ESC
      break;
    }
  }

  return 0;
}
