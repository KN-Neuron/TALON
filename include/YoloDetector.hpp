#pragma once

#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <opencv2/dnn.hpp>

// ============================================================================
// DETEKTOR YOLO (OpenCV DNN)
// ============================================================================

// 'inline' pozwala trzymac definicje w naglowku bez naruszenia ODR
// (naglowek jest wlaczany przez wiele jednostek kompilacji).
inline const std::vector<std::string> COCO_CLASSES = {
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

std::string getClassName(int class_id);

double getRealWidthForClass(int class_id);
double getRealHeightForClass(int class_id);
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
  YoloDetector(const std::string &model_path);

  std::vector<Detection> detect(const cv::Mat &frame);
};
