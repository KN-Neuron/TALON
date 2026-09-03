#pragma once

#include <opencv2/core.hpp>

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
  KalmanFilter2D();

  void init(double initial_z);

  bool isInitialized() const { return initialized; }

  // Faza 1: Project (Fizyka drona)
  void predict(double dt);

  // Faza 2: Update (Korekta z kamery)
  void update(double z_meas);

  double getZ() const { return x_hat(0, 0); }
  double getZDot() const { return x_hat(1, 0); }
};

struct TrackedObject {
  int id;
  int class_id;
  KalmanFilter2D kalman;
  int time_since_update;

  // Ostatnia detekcja przypisana do tego sladu. Trzymamy ja przy obiekcie,
  // zeby renderowanie i nadawanie nie musialy ponownie parowac sladow z
  // detekcjami — parowanie odbywa sie raz, w fazie asocjacji.
  cv::Rect last_box;
  float last_confidence = 0.0f;
  double last_lateral_m = 0.0;
};
