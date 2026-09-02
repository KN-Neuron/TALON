cmake_minimum_required(VERSION 3.16)
project(TALON LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Baza kompilacji dla LSP (clangd w nvim/VSCode) — bez niej serwer nie zna
# sciezek do naglowkow OpenCV i zglasza falszywe bledy.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(OpenCV REQUIRED)

add_executable(testcv
  src/main.cpp
  src/YoloDetector.cpp
  src/KalmanFilter2D.cpp
  src/OccupancyGrid2D.cpp
)

target_link_libraries(testcv PRIVATE ${OpenCV_LIBS})
target_include_directories(testcv PRIVATE
  ${OpenCV_INCLUDE_DIRS}
  ${CMAKE_CURRENT_SOURCE_DIR}/include
)
