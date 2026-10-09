#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"
#include "mc_hal.h"

static const char *TAG = "mc_adc";

static const mc_board_t *board;
static adc_oneshot_unit_handle_t unit;
static adc_cali_handle_t cali;
static bool channel_ready[SOC_ADC_MAX_CHANNEL_NUM];

void mc_hal_adc_init(const mc_board_t *b)
{
    board = b;
    adc_oneshot_unit_init_cfg_t cfg = {.unit_id = ADC_UNIT_1};
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&cfg, &unit));
    adc_cali_curve_fitting_config_t cc = {
        .unit_id = ADC_UNIT_1, .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    if (adc_cali_create_scheme_curve_fitting(&cc, &cali) != ESP_OK) {
        cali = NULL;
        ESP_LOGW(TAG, "no ADC calibration, battery voltage is approximate");
    }
}

static bool channel_of(int gpio, adc_channel_t *ch)
{
    adc_unit_t u;
    if (gpio < 0 || adc_oneshot_io_to_channel(gpio, &u, ch) != ESP_OK || u != ADC_UNIT_1) {
        return false;
    }
    if (!channel_ready[*ch]) {
        adc_oneshot_chan_cfg_t cc = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
        if (adc_oneshot_config_channel(unit, *ch, &cc) != ESP_OK) {
            return false;
        }
        channel_ready[*ch] = true;
    }
    return true;
}

static bool average(int gpio, uint8_t samples, int *out)
{
    adc_channel_t ch;
    if (!channel_of(gpio, &ch)) {
        return false;
    }
    if (samples < 1) {
        samples = 1;
    }
    int sum = 0;
    for (uint8_t i = 0; i < samples; i++) {
        int v;
        if (adc_oneshot_read(unit, ch, &v) != ESP_OK) {
            return false;
        }
        sum += v;
    }
    *out = sum / samples;
    return true;
}

bool mc_hal_adc_read_port(uint8_t port, uint8_t samples, uint16_t *raw)
{
    int gpio;
    if (port & MC_PORT_RAW_FLAG) {
        gpio = port & 0x7F;
    } else if (board != NULL && port < board->port_count) {
        gpio = board->ports[port].gpio;
    } else {
        return false;
    }
    int v;
    if (!average(gpio, samples, &v)) {
        return false;
    }
    *raw = (uint16_t)v;
    return true;
}

uint16_t mc_hal_battery_mv(void)
{
    int raw;
    if (board == NULL || board->battery_gpio < 0 || !average(board->battery_gpio, 8, &raw)) {
        return 0;
    }
    int mv = raw * 3300 / 4095; /* without calibration: a rough linear estimate */
    if (cali != NULL) {
        adc_cali_raw_to_voltage(cali, raw, &mv);
    }
    return (uint16_t)(mv * board->battery_divider_x100 / 100);
}
