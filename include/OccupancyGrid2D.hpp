#pragma once

#include <opencv2/core.hpp>

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
  OccupancyGrid2D(double cellSize = 0.1, double maxRange = 10.0);

  void clear();

  // Rzutowanie punktu (X, Z) na siatkę BEV
  void insertObstacle(double X, double Z);

  // Wizualizacja siatki BEV w małym oknie OpenCV
  cv::Mat render() const;
};
