if(CONFIG_MC_ZIGBEE_STUB)
    set(srcs src/zb_stub.c)
    set(priv log esp_system)
else()
    set(srcs src/zb_sdk.c)
    set(priv log esp_system esp_timer heap nvs_flash espressif__esp-zigbee-lib espressif__esp-zboss-lib)
endif()
idf_component_register(
    SRCS ${srcs}
    INCLUDE_DIRS include
    REQUIRES mc_core mc_hal
    PRIV_REQUIRES ${priv}
)
