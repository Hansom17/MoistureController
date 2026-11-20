# ESP-IDF component and, through test/CMakeLists.txt, the sources of the host tests.
idf_component_register(
    SRCS
        src/mc_boards_table.c
        src/mc_cfg.c
        src/mc_cmd.c
        src/mc_config.c
        src/mc_core.c
        src/mc_factory.c
        src/mc_moisture.c
        src/mc_power.c
        src/mc_sense.c
        src/mc_ui.c
    INCLUDE_DIRS include
    PRIV_INCLUDE_DIRS src
)
