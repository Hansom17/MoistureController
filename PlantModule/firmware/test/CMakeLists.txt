# Host tests of mc_core (PlantModule/specs.md 16): plain C, Unity, fake clock and fake I/O. No ESP-IDF needed.
#   cmake -S PlantModule/firmware/test -B /tmp/mc_host && cmake --build /tmp/mc_host && ctest --test-dir /tmp/mc_host
cmake_minimum_required(VERSION 3.16)
project(mc_core_host_tests C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -Wshadow -Wconversion -Wno-sign-conversion -Werror -fsanitize=address,undefined -fno-omit-frame-pointer)
add_link_options(-fsanitize=address,undefined)

set(CORE ${CMAKE_CURRENT_LIST_DIR}/../components/mc_core)
add_library(mc_core STATIC
    ${CORE}/src/mc_boards_table.c ${CORE}/src/mc_cfg.c ${CORE}/src/mc_cmd.c ${CORE}/src/mc_config.c
    ${CORE}/src/mc_core.c ${CORE}/src/mc_factory.c ${CORE}/src/mc_moisture.c ${CORE}/src/mc_power.c ${CORE}/src/mc_sense.c
    ${CORE}/src/mc_ui.c)
target_include_directories(mc_core PUBLIC ${CORE}/include PRIVATE ${CORE}/src)

add_library(unity STATIC unity/unity.c)
target_include_directories(unity PUBLIC unity)
target_compile_options(unity PRIVATE -Wno-conversion -Wno-shadow -Wno-error)

file(GLOB TESTS ${CMAKE_CURRENT_LIST_DIR}/test_*.c)
add_executable(mc_host_tests main.c support/sim.c ${TESTS})
target_include_directories(mc_host_tests PRIVATE support ${CORE}/src)
target_link_libraries(mc_host_tests mc_core unity)

enable_testing()
add_test(NAME host_tests COMMAND mc_host_tests)
