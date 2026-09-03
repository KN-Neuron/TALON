#include "FrameServer.hpp"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <iostream>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace frameshm {

std::string segmentName(const std::string &stream_name) {
  // POSIX wymaga wiodacego ukosnika i zabrania kolejnych w srodku nazwy.
  return "/talon." + stream_name;
}

} // namespace frameshm

namespace {

int64_t nowMillis() {
  using namespace std::chrono;
  return duration_cast<milliseconds>(system_clock::now().time_since_epoch())
      .count();
}

// Wyrownanie do strony pamieci — sloty zaczynaja sie na granicy strony, wiec
// zapis do jednego nie unieważnia linii cache sasiada.
size_t alignUp(size_t value, size_t alignment) {
  return (value + alignment - 1) / alignment * alignment;
}

} // namespace

FrameServer::FrameServer(const std::string &stream_name, int max_width,
                         int max_height, int channels)
    : segment_name_(frameshm::segmentName(stream_name)), max_width_(max_width),
      max_height_(max_height), channels_(channels) {

  const size_t frame_bytes =
      static_cast<size_t>(max_width) * max_height * channels;
  slot_stride_ = alignUp(sizeof(frameshm::SlotHeader) + frame_bytes, 4096);
  mapping_bytes_ =
      alignUp(sizeof(frameshm::SegmentHeader), 4096) +
      slot_stride_ * frameshm::kSlotCount;

  // Segment po poprzednim uruchomieniu moze miec inny rozmiar, wiec zaczynamy
  // od czystego miejsca.
  ::shm_unlink(segment_name_.c_str());

  fd_ = ::shm_open(segment_name_.c_str(), O_CREAT | O_RDWR | O_EXCL, 0644);
  if (fd_ < 0) {
    std::cerr << "[klatki] Nie udalo sie utworzyc " << segment_name_ << ": "
              << std::strerror(errno) << "\n";
    return;
  }

  if (::ftruncate(fd_, static_cast<off_t>(mapping_bytes_)) != 0) {
    std::cerr << "[klatki] Nie udalo sie ustawic rozmiaru segmentu: "
              << std::strerror(errno) << "\n";
    ::close(fd_);
    fd_ = -1;
    ::shm_unlink(segment_name_.c_str());
    return;
  }

  mapping_ = ::mmap(nullptr, mapping_bytes_, PROT_READ | PROT_WRITE, MAP_SHARED,
                    fd_, 0);
  if (mapping_ == MAP_FAILED) {
    std::cerr << "[klatki] mmap nie powiodl sie: " << std::strerror(errno)
              << "\n";
    mapping_ = nullptr;
    ::close(fd_);
    fd_ = -1;
    ::shm_unlink(segment_name_.c_str());
    return;
  }

  auto *header = static_cast<frameshm::SegmentHeader *>(mapping_);
  header->slot_count = frameshm::kSlotCount;
  header->slot_stride = static_cast<uint32_t>(slot_stride_);
  header->max_width = static_cast<uint32_t>(max_width);
  header->max_height = static_cast<uint32_t>(max_height);
  header->max_channels = static_cast<uint32_t>(channels);
  header->latest_slot = 0;
  header->layout_version = frameshm::kLayoutVersion;

  // magic na koncu: dopiero jego obecnosc oznacza, ze reszta naglowka jest
  // wypelniona, wiec czytelnik nie zobaczy polowicznie gotowego segmentu.
  std::atomic_thread_fence(std::memory_order_release);
  header->magic = frameshm::kMagic;

  std::cout << "[klatki] Udostepniam " << segment_name_ << " (" << max_width
            << "x" << max_height << ", " << frameshm::kSlotCount
            << " slotow)\n";
}

FrameServer::~FrameServer() {
  if (mapping_ != nullptr) {
    ::munmap(mapping_, mapping_bytes_);
  }
  if (fd_ >= 0) {
    ::close(fd_);
    // Bez tego segment zostaje w systemie po zamknieciu programu.
    ::shm_unlink(segment_name_.c_str());
  }
}

bool FrameServer::publish(const cv::Mat &frame, uint64_t frame_id) {
  if (mapping_ == nullptr || frame.empty()) {
    return false;
  }

  // Segment ma staly rozmiar — wieksza klatka nie zmiesci sie w slocie.
  if (frame.cols > max_width_ || frame.rows > max_height_ ||
      frame.channels() != channels_) {
    return false;
  }
  // cv::Mat bywa niecialy (ROI, wycinek); kopiujemy wiersz po wierszu tylko
  // wtedy, gdy trzeba.
  const size_t row_bytes = static_cast<size_t>(frame.cols) * frame.channels();
  const size_t frame_bytes = row_bytes * frame.rows;

  auto *base = static_cast<uint8_t *>(mapping_);
  auto *header = reinterpret_cast<frameshm::SegmentHeader *>(base);

  uint8_t *slot_base =
      base + alignUp(sizeof(frameshm::SegmentHeader), 4096) +
      slot_stride_ * next_slot_;
  auto *slot = reinterpret_cast<frameshm::SlotHeader *>(slot_base);
  uint8_t *pixels = slot_base + sizeof(frameshm::SlotHeader);

  // Nieparzysta sekwencja = "nie czytaj, pisze".
  ++slot->sequence;
  std::atomic_thread_fence(std::memory_order_release);

  slot->width = static_cast<uint32_t>(frame.cols);
  slot->height = static_cast<uint32_t>(frame.rows);
  slot->channels = static_cast<uint32_t>(frame.channels());
  slot->frame_id = frame_id;
  slot->timestamp_ms = nowMillis();
  slot->data_bytes = static_cast<uint32_t>(frame_bytes);

  if (frame.isContinuous()) {
    std::memcpy(pixels, frame.data, frame_bytes);
  } else {
    for (int row = 0; row < frame.rows; ++row) {
      std::memcpy(pixels + row * row_bytes, frame.ptr(row), row_bytes);
    }
  }

  // Dane musza byc widoczne zanim sekwencja zrobi sie parzysta, inaczej
  // czytelnik uzna niekompletna klatke za gotowa.
  std::atomic_thread_fence(std::memory_order_release);
  ++slot->sequence;

  std::atomic_thread_fence(std::memory_order_release);
  header->latest_slot = static_cast<uint32_t>(next_slot_);

  next_slot_ = (next_slot_ + 1) % frameshm::kSlotCount;
  ++frames_published_;
  return true;
}
