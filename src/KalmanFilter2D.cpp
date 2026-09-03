#include "KalmanFilter2D.hpp"

KalmanFilter2D::KalmanFilter2D() : initialized(false) {
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

void KalmanFilter2D::init(double initial_z) {
  x_hat(0, 0) = initial_z;
  x_hat(1, 0) = 0.0; // Prędkość początkowa = 0
  initialized = true;
}

// Faza 1: Project (Fizyka drona)
void KalmanFilter2D::predict(double dt) {
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
void KalmanFilter2D::update(double z_meas) {
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
