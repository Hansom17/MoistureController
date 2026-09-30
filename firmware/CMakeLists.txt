# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.28.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(moisture-controller)

# Hardware independent logic: unit-tested on QEMU (tests/core).
file(GLOB CORE_SOURCES CONFIGURE_DEPENDS src/core/*.c)
file(GLOB HAL_SOURCES CONFIGURE_DEPENDS src/hal/*.c)
target_sources(app PRIVATE src/main.c ${CORE_SOURCES} ${HAL_SOURCES})
target_include_directories(app PRIVATE src src/core src/hal)
