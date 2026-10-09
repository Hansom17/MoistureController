idf_component_register(
    SRCS src/zb_stub.c
    INCLUDE_DIRS include
    REQUIRES mc_core mc_hal
    PRIV_REQUIRES log esp_system
)
