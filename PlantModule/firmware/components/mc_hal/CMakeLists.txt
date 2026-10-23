idf_component_register(
    SRCS src/hal_store.c src/hal_gpio.c src/hal_adc.c src/hal_timers.c
    INCLUDE_DIRS include
    REQUIRES mc_core
    PRIV_REQUIRES nvs_flash esp_partition esp_adc esp_driver_gpio esp_timer esp_system log
)
