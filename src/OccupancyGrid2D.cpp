#include "OccupancyGrid2D.hpp"

#include <cstring>

#include <opencv2/imgproc.hpp>

OccupancyGrid2D::OccupancyGrid2D(double cellSize, double maxRange)
    : cell_size(cellSize), max_range(maxRange) {
  clear();
}

void OccupancyGrid2D::clear() { std::memset(grid, 0, sizeof(grid)); }

// Rzutowanie punktu (X, Z) na siatkę BEV
void OccupancyGrid2D::insertObstacle(double X, double Z) {
  if (Z <= 0.0 || Z >= max_range)
    return;

  // Mapowanie: X od [-max_range/2, max_range/2] na [0, GRID_SIZE]
  int grid_x = static_cast<int>((X + (max_range / 2.0)) / cell_size);
  int grid_z = static_cast<int>(Z / cell_size);

  if (grid_x >= 0 && grid_x < GRID_SIZE && grid_z >= 0 && grid_z < GRID_SIZE) {
    grid[grid_z][grid_x] = 1; // Oznaczenie komórki jako zajętej
  }
}

// Wizualizacja siatki BEV w małym oknie OpenCV
cv::Mat OccupancyGrid2D::render() const {
  cv::Mat vis = cv::Mat::zeros(GRID_SIZE * 2, GRID_SIZE * 2, CV_8UC3);
  for (int z = 0; z < GRID_SIZE; ++z) {
    for (int x = 0; x < GRID_SIZE; ++x) {
      if (grid[z][x] > 0) {
        cv::rectangle(vis, cv::Rect(x * 2, (GRID_SIZE - 1 - z) * 2, 2, 2),
                      cv::Scalar(0, 0, 255), -1);
      }
    }
  }
  // Pozycja drona (na dole, w środku)
  cv::circle(vis, cv::Point(GRID_SIZE, GRID_SIZE * 2 - 5), 3,
             cv::Scalar(0, 255, 0), -1);
  return vis;
}
