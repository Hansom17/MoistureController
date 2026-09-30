cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(mc_core_tests)

set(CORE ${CMAKE_CURRENT_LIST_DIR}/../../src/core)
file(GLOB CORE_SOURCES CONFIGURE_DEPENDS ${CORE}/*.c)
file(GLOB TEST_SOURCES CONFIGURE_DEPENDS src/*.c)
target_sources(app PRIVATE ${CORE_SOURCES} ${TEST_SOURCES})
target_include_directories(app PRIVATE ${CORE} ${CMAKE_CURRENT_BINARY_DIR})

# The contract's own examples (contracts/mqtt.md) become test inputs.
find_package(Python3 REQUIRED)
execute_process(COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_LIST_DIR}/../../scripts/gen_contract_examples.py
    ${CMAKE_CURRENT_BINARY_DIR}/contract_examples.h
    COMMAND_ERROR_IS_FATAL ANY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    ${CMAKE_CURRENT_LIST_DIR}/../../../contracts/mqtt.md
    ${CMAKE_CURRENT_LIST_DIR}/../../../contracts/ble_vectors.json
    ${CMAKE_CURRENT_LIST_DIR}/../../scripts/gen_contract_examples.py)
