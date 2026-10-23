#include <string.h>

#include "esp_log.h"
#include "mc_app.h"
#include "mc_hal.h"
#include "sdkconfig.h"

static const char *TAG = "main";

void app_main(void)
{
    mc_hal_store_init();

    mc_factory_t factory;
    bool valid = mc_hal_factory_read(&factory);
    const mc_board_t *board = NULL;
    if (valid) {
        board = mc_board_find(factory.board);
        ESP_LOGI(TAG, "factory data: board %s, serial %s", factory.board, factory.serial);
    } else if (strlen(CONFIG_MC_DEV_BOARD) > 0) {
        /* Development only: a board without factory data runs as the configured board. */
        board = mc_board_find(CONFIG_MC_DEV_BOARD);
        memset(&factory, 0, sizeof factory);
        strncpy(factory.board, CONFIG_MC_DEV_BOARD, sizeof factory.board - 1);
        strncpy(factory.serial, "DEV", sizeof factory.serial - 1);
        valid = board != NULL;
        ESP_LOGW(TAG, "no factory data, running as development board %s", CONFIG_MC_DEV_BOARD);
    } else {
        ESP_LOGE(TAG, "factory data invalid: safe mode");
    }
    if (valid && board == NULL) {
        ESP_LOGE(TAG, "unknown board %s: safe mode", factory.board);
    }
    mc_app_start(board, &factory, valid);
}
