// Testy funkcji czysto geometrycznych i nadajnika detekcji.
//
// Bez frameworka: prosty main() z asercjami, zeby nie dokladac zaleznosci.
// Uruchomienie:
//     ./run.sh test

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

#include "Config.hpp"
#include "KalmanFilter2D.hpp"
#include "PerceptionMath.hpp"

namespace {

int failures = 0;

void check(bool condition, const std::string &name) {
  if (condition) {
    std::cout << "  ok   " << name << "\n";
  } else {
    std::cout << "  FAIL " << name << "\n";
    ++failures;
  }
}

void checkNear(double actual, double expected, double tolerance,
               const std::string &name) {
  const bool ok = std::fabs(actual - expected) <= tolerance;
  if (!ok) {
    std::cout << "  FAIL " << name << " (oczekiwano " << expected << ", jest "
              << actual << ")\n";
    ++failures;
  } else {
    std::cout << "  ok   " << name << "\n";
  }
}

// --- calculateDepth ---------------------------------------------------------

void testDepth() {
  std::cout << "calculateDepth:\n";

  // Z = (fx * W) / w. Butelka 8cm szeroka, 40px w kadrze, fx=500 -> 1.0m
  checkNear(PerceptionMath::calculateDepth(500.0, 0.08, 40.0), 1.0, 1e-9,
            "obiekt 8cm/40px przy fx=500 to 1m");

  // Dwa razy wezszy box = dwa razy dalej.
  checkNear(PerceptionMath::calculateDepth(500.0, 0.08, 20.0), 2.0, 1e-9,
            "polowa szerokosci to podwojna odleglosc");

  // Dzielenie przez zero musi byc obsluzone, nie dawac inf.
  check(PerceptionMath::calculateDepth(500.0, 0.5, 0.0) == 0.0,
        "zerowa szerokosc boxa zwraca 0, nie inf");
  check(PerceptionMath::calculateDepth(500.0, 0.5, -5.0) == 0.0,
        "ujemna szerokosc boxa zwraca 0");
}

// --- calculateX -------------------------------------------------------------

void testLateral() {
  std::cout << "calculateX:\n";

  // Obiekt w srodku kadru nie ma odchylenia bocznego.
  checkNear(PerceptionMath::calculateX(320.0, 320.0, 5.0, 500.0), 0.0, 1e-9,
            "obiekt w srodku kadru ma X=0");

  // Na prawo od srodka -> dodatnie X.
  check(PerceptionMath::calculateX(500.0, 320.0, 5.0, 500.0) > 0.0,
        "obiekt na prawo ma X dodatnie");

  // Na lewo -> ujemne. To konwencja, na ktorej opiera sie nakladka.
  check(PerceptionMath::calculateX(100.0, 320.0, 5.0, 500.0) < 0.0,
        "obiekt na lewo ma X ujemne");

  // X rosnie liniowo z odlegloscia przy tym samym odchyleniu w pikselach.
  const double bliski = PerceptionMath::calculateX(420.0, 320.0, 2.0, 500.0);
  const double daleki = PerceptionMath::calculateX(420.0, 320.0, 4.0, 500.0);
  checkNear(daleki, bliski * 2.0, 1e-9, "X skaluje sie liniowo z Z");
}

// --- calculateTTC -----------------------------------------------------------

void testTimeToCollision() {
  std::cout << "calculateTTC:\n";

  // 10m przy zblizaniu 2m/s -> 5s.
  checkNear(PerceptionMath::calculateTTC(10.0, -2.0), 5.0, 1e-9,
            "10m przy -2m/s to 5s");

  // Obiekt oddalajacy sie nie ma sensownego TTC — wartownik 999.
  check(PerceptionMath::calculateTTC(10.0, 1.5) == 999.0,
        "obiekt oddalajacy sie dostaje wartownik 999");
  check(PerceptionMath::calculateTTC(10.0, 0.0) == 999.0,
        "obiekt nieruchomy dostaje wartownik 999");

  // Ledwie zauwazalne zblizanie tez jest traktowane jak brak ruchu
  // (prog -0.01), inaczej TTC skakaloby do absurdalnych wartosci przy szumie.
  check(PerceptionMath::calculateTTC(10.0, -0.005) == 999.0,
        "szum ponizej progu nie generuje TTC");
}

// --- CameraParams -----------------------------------------------------------

void testCameraParams() {
  std::cout << "CameraParams::updateResolution:\n";

  CameraParams camera;
  camera.h_fov_deg = 60.0;
  camera.updateResolution(640, 480);

  checkNear(camera.cx, 320.0, 1e-9, "cx to polowa szerokosci");
  // fx = W / (2*tan(FOV/2)); dla 640px i 60 stopni to ~554.
  checkNear(camera.fx, 640.0 / (2.0 * std::tan(30.0 * M_PI / 180.0)), 1e-9,
            "fx wyliczone z FOV");

  // Szerszy kadr przy tym samym FOV daje wieksze fx.
  CameraParams wide;
  wide.h_fov_deg = 60.0;
  wide.updateResolution(1280, 720);
  check(wide.fx > camera.fx, "wieksza rozdzielczosc daje wieksze fx");
  checkNear(wide.cx, 640.0, 1e-9, "cx nadaza za rozdzielczoscia");
}

// --- KalmanFilter2D ---------------------------------------------------------

void testKalman() {
  std::cout << "KalmanFilter2D:\n";

  KalmanFilter2D filter;
  check(!filter.isInitialized(), "swiezy filtr jest nieziniciowany");

  filter.init(5.0);
  check(filter.isInitialized(), "po init filtr jest gotowy");
  checkNear(filter.getZ(), 5.0, 1e-9, "init ustawia pozycje");
  checkNear(filter.getZDot(), 0.0, 1e-9, "init zaklada zerowa predkosc");

  // Obiekt zbliza sie o 0.1m na klatke (30 fps => -3 m/s).
  // Po serii spojnych pomiarow filtr powinien wykryc ujemna predkosc.
  double z = 5.0;
  for (int i = 0; i < 40; ++i) {
    z -= 0.1;
    filter.predict(1.0 / 30.0);
    filter.update(z);
  }

  check(filter.getZDot() < 0.0, "filtr wykrywa zblizanie (ujemna predkosc)");
  checkNear(filter.getZ(), z, 0.3, "estymata podaza za pomiarami");

  // Sama predykcja bez pomiaru musi przesuwac pozycje zgodnie z predkoscia.
  const double before = filter.getZ();
  filter.predict(0.5);
  check(filter.getZ() < before,
        "predykcja bez pomiaru kontynuuje ruch obiektu");
}

} // namespace

int main() {
  testDepth();
  testLateral();
  testTimeToCollision();
  testCameraParams();
  testKalman();

  std::cout << "\n";
  if (failures == 0) {
    std::cout << "Wszystkie testy przeszly.\n";
    return 0;
  }
  std::cout << failures << " test(ow) nie przeszlo.\n";
  return 1;
}
