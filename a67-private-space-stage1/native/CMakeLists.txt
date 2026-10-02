cmake_minimum_required(VERSION 3.22)
project(a67_private_space_stage1 LANGUAGES CXX)

add_library(a67psflag SHARED main.cpp)

target_include_directories(a67psflag PRIVATE include)
target_compile_features(a67psflag PRIVATE cxx_std_17)
target_compile_options(a67psflag PRIVATE
    -fvisibility=hidden
    -fvisibility-inlines-hidden
    -fno-exceptions
    -fno-rtti
    -Wall
    -Wextra
)

find_library(log-lib log)
target_link_libraries(a67psflag PRIVATE ${log-lib})
