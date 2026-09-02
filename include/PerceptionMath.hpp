#pragma once

// Modul przeliczania czysto geometrycznego (header-only).
// Funkcje sa inline, wiec nie maja odpowiednika .cpp.

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
