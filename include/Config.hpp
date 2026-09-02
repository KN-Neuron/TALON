#pragma once

// Parametry uruchomieniowe i model kamery (header-only).
// std::tan / M_PI w updateResolution:
#include <cmath>

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
