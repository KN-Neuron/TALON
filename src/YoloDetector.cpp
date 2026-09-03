#include "YoloDetector.hpp"

#include <opencv2/imgproc.hpp>

std::string getClassName(int class_id) {
  if (class_id >= 0 && class_id < static_cast<int>(COCO_CLASSES.size())) {
    return COCO_CLASSES[class_id];
  }
  return "unknown";
}
double getRealHeightForClass(int class_id) {
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

YoloDetector::YoloDetector(const std::string &model_path) {
  // Wczytanie modelu ONNX przez silnik OpenCV DNN
  net = cv::dnn::readNetFromONNX(model_path);

  // Jeśli masz GPU/CUDA na laptopie, możesz odblokować poniższe 2 linie:
  // net.setPreferableBackend(cv::dnn::DNN_BACKEND_CUDA);
  // net.setPreferableTarget(cv::dnn::DNN_TARGET_CUDA);
  net.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);
  net.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);
}

std::vector<Detection> YoloDetector::detect(const cv::Mat &frame) {
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
    cv::minMaxLoc(cv::Mat(1, 80, CV_32F, const_cast<float *>(scores)), nullptr,
                  &max_score, nullptr, &class_id_point);

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
  cv::dnn::NMSBoxes(boxes, confidences, conf_threshold, nms_threshold, indices);

  for (int idx : indices) {
    detections.push_back({class_ids[idx], confidences[idx], boxes[idx]});
  }

  return detections;
}
