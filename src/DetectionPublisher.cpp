#include "DetectionPublisher.hpp"

#include <cerrno>
#include <chrono>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <locale>
#include <sstream>

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace {

// Wersja schematu z docs/detection-protocol.md. Podbijamy przy kazdej zmianie
// lamiacej zgodnosc — odbiorcy ignoruja wersje, ktorych nie znaja.
constexpr int kSchemaVersion = 1;

// Czas scienny w milisekundach. Nie jest zsynchronizowany z osia czasu wideo,
// wiec nakladka wyprzedza obraz o opoznienie transmisji (patrz "Clocks" w
// dokumentacji protokolu).
long nowMillis() {
  using namespace std::chrono;
  return duration_cast<milliseconds>(system_clock::now().time_since_epoch())
      .count();
}

// JSON wymaga kropki dziesietnej, a domyslny locale programu moze uzywac
// przecinka (np. pl_PL) — wtedy odbiorca dostalby niepoprawny dokument.
void writeDouble(std::ostringstream &out, double value, int precision) {
  std::ostringstream field;
  field.imbue(std::locale::classic());
  field << std::fixed << std::setprecision(precision) << value;
  out << field.str();
}

// Ucieczka znakow w nazwie klasy. Nazwy COCO sa bezpieczne, ale wlasny model
// moze miec cudzyslow albo ukosnik w etykiecie.
std::string escapeJson(const std::string &text) {
  std::string escaped;
  escaped.reserve(text.size());
  for (char c : text) {
    switch (c) {
    case '"':
      escaped += "\\\"";
      break;
    case '\\':
      escaped += "\\\\";
      break;
    case '\n':
      escaped += "\\n";
      break;
    case '\r':
      escaped += "\\r";
      break;
    case '\t':
      escaped += "\\t";
      break;
    default:
      escaped += c;
    }
  }
  return escaped;
}

} // namespace

DetectionPublisher::DetectionPublisher(const std::string &socket_path)
    : socket_path_(socket_path) {
  if (socket_path.empty()) {
    return; // nadawanie wylaczone
  }

  // Sciezka gniazda trafia do sun_path o stalym rozmiarze — dluzsza zostalaby
  // po cichu obcieta i program pisalby w zle miejsce.
  sockaddr_un address{};
  if (socket_path.size() >= sizeof(address.sun_path)) {
    std::cerr << "[detekcje] Sciezka gniazda za dluga (max "
              << sizeof(address.sun_path) - 1 << " znakow): " << socket_path
              << "\n";
    return;
  }

  fd_ = ::socket(AF_UNIX, SOCK_DGRAM, 0);
  if (fd_ < 0) {
    std::cerr << "[detekcje] Nie udalo sie otworzyc gniazda: "
              << std::strerror(errno) << "\n";
    return;
  }

  std::cout << "[detekcje] Nadaje na " << socket_path << "\n";
}

DetectionPublisher::~DetectionPublisher() {
  if (fd_ >= 0) {
    ::close(fd_);
  }
}

std::string DetectionPublisher::buildJson(
    const std::vector<DetectionMessage> &objects, int image_width,
    int image_height, double frame_interval_s) const {
  std::ostringstream json;
  json.imbue(std::locale::classic());

  json << "{\"version\":" << kSchemaVersion << ",\"frame_id\":" << frame_id_
       << ",\"timestamp_ms\":" << nowMillis() << ",\"frame_interval_s\":";
  writeDouble(json, frame_interval_s, 4);
  json << ",\"image_width\":" << image_width
       << ",\"image_height\":" << image_height << ",\"objects\":[";

  bool first = true;
  for (const auto &object : objects) {
    if (!first) {
      json << ',';
    }
    first = false;

    json << "{\"track_id\":" << object.track_id
         << ",\"class_id\":" << object.class_id << ",\"class_name\":\""
         << escapeJson(object.class_name) << "\",\"confidence\":";
    writeDouble(json, object.confidence, 3);

    json << ",\"box\":{\"left\":" << object.box.x
         << ",\"top\":" << object.box.y << ",\"width\":" << object.box.width
         << ",\"height\":" << object.box.height << '}';

    if (object.has_position) {
      json << ",\"position\":{\"lateral_m\":";
      writeDouble(json, object.lateral_m, 3);
      json << ",\"forward_m\":";
      writeDouble(json, object.forward_m, 3);
      json << '}';
    }

    if (object.has_ttc) {
      json << ",\"closing_speed_mps\":";
      writeDouble(json, object.closing_speed_mps, 3);
      json << ",\"time_to_collision_s\":";
      writeDouble(json, object.time_to_collision_s, 2);
    }

    json << ",\"frames_since_seen\":" << object.frames_since_seen << '}';
  }

  json << "]}";
  return json.str();
}

bool DetectionPublisher::publish(const std::vector<DetectionMessage> &objects,
                                 int image_width, int image_height,
                                 double frame_interval_s) {
  if (fd_ < 0) {
    return false;
  }

  const std::string payload =
      buildJson(objects, image_width, image_height, frame_interval_s);
  ++frame_id_;

  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  std::strncpy(address.sun_path, socket_path_.c_str(),
               sizeof(address.sun_path) - 1);

  // MSG_DONTWAIT: petla detekcji nigdy nie czeka na odbiorce.
  const ssize_t sent =
      ::sendto(fd_, payload.data(), payload.size(), MSG_DONTWAIT,
               reinterpret_cast<sockaddr *>(&address), sizeof(address));

  if (sent < 0) {
    ++frames_dropped_;

    // ENOENT/ECONNREFUSED = klient jeszcze nie wystartowal. To normalne, wiec
    // mowimy o tym raz, a nie co klatke.
    if (errno == ENOENT || errno == ECONNREFUSED) {
      if (!warned_no_listener_) {
        std::cout << "[detekcje] Brak odbiorcy na " << socket_path_
                  << " — czekam (uruchom apps/client)\n";
        warned_no_listener_ = true;
      }
    }
    return false;
  }

  if (warned_no_listener_) {
    std::cout << "[detekcje] Odbiorca podlaczony\n";
    warned_no_listener_ = false;
  }

  ++frames_sent_;
  return true;
}
