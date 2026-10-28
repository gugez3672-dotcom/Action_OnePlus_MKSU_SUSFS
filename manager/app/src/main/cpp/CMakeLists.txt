
# For more information about using CMake with Android Studio, read the
# documentation: https://d.android.com/studio/projects/add-native-code.html

# Sets the minimum version of CMake required to build the native library.
cmake_minimum_required(VERSION 3.18.1)

project("note_bridge")

find_package(cxx REQUIRED CONFIG)
link_libraries(cxx::cxx)

add_library(note_bridge
        SHARED
        jni.cc
        ksu.cc
        )

target_include_directories(note_bridge PRIVATE .)

find_library(log-lib log)

target_link_libraries(note_bridge ${log-lib})

add_library(note_connect SHARED connect.cc)
target_link_libraries(note_connect ${log-lib})
