cmake_minimum_required(VERSION 3.22)
project(a67_private_space_stage3 LANGUAGES CXX)

add_library(a67pslauncher SHARED main.cpp)
target_include_directories(a67pslauncher PRIVATE include)
target_compile_features(a67pslauncher PRIVATE cxx_std_17)
target_compile_options(a67pslauncher PRIVATE
    -fvisibility=hidden
    -fvisibility-inlines-hidden
    -fno-exceptions
    -fno-rtti
    -Wall
    -Wextra
)
find_library(log-lib log)
target_link_libraries(a67pslauncher PRIVATE ${log-lib})
