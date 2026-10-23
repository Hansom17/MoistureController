/* The Zigbee side on esp-zigbee-sdk (PlantModule/specs.md 8, Part B): an end device that keeps its receiver on,
 * one endpoint with Basic, Identify, Power configuration and the custom cluster 0xFC11 of interface.yaml.
 *
 * Threads: the stack runs in its own task. Everything here that touches the stack from another task holds the
 * stack lock. Callbacks of the stack only translate into mc_event_t and post them (mc_app_post); no application
 * code runs in the Zigbee task. */
#include <string.h>

#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_zigbee_core.h"
#include "nvs.h"
#include "ha/esp_zigbee_ha_standard.h"
#include "zcl/esp_zigbee_zcl_power_config.h"
#include "mc_hal.h"
#include "mc_zigbee.h"
#include "nvs_flash.h"

static const char *TAG = "mc_zb";

#define EP MC_ENDPOINT
#define SRV ESP_ZB_ZCL_CLUSTER_SERVER_ROLE
#define MANUF MC_MANUFACTURER_CODE

static mc_zb_params_t params;
static mc_factory_t factory_copy;
static bool have_factory;
static bool rejoining;
static bool join_seen_configured;
static bool reporting_stale; /* the registered attribute set differs from the one the stored records belong to */
static volatile bool stack_up; /* the endpoint is registered and the stack runs: attributes can be set and reported */
static uint16_t configure_polls;
static uint32_t attr_set_hash; /* of everything registered below: when it changes the stack's stored records are stale */

/* ---- attribute storage (the stack keeps pointers to these) --------------------------------------------- */

static struct {
    uint16_t seq, boot_id;
    uint8_t slot[MC_NUM_SLOTS][9];     /* octet string: length byte + 8 */
    uint8_t status, fast_mode, safe_reason;
    uint32_t uptime_s;
    uint8_t boot_reason;
    uint16_t reset_count, rejoin_count, last_error;
    uint32_t free_heap;
    uint16_t interface_version;
    uint8_t config_schema;
    uint8_t board[17];                 /* char string: length byte + 16 */
    uint16_t cfg_rev;
    uint8_t cfg_result;
    uint16_t cfg_error;
    uint16_t report_interval_s, fast_report_interval_s, fast_report_hold_s, batt_low_mv;
    uint16_t batt_critical_mv, batt_cal_permille;
    uint16_t batt_mv;
    uint8_t batt_state;
    uint8_t slot_cfg[MC_NUM_SLOTS][25]; /* octet string: length byte + up to 24 */
    uint8_t batt_100mv;
} store;

static void post(const mc_event_t *ev)
{
    mc_app_post(ev);
}

static void post_simple(mc_ev_kind_t kind)
{
    mc_event_t ev = {.kind = kind};
    post(&ev);
}

static void post_bool(mc_ev_kind_t kind, bool v)
{
    mc_event_t ev = {.kind = kind};
    ev.u.ok = v;
    post(&ev);
}

/* ---- endpoint ----------------------------------------------------------------------------------------- */

static uint16_t rep_ids[48];
static size_t rep_count;

static void mix(uint32_t v)
{
    attr_set_hash = (attr_set_hash ^ v) * 16777619u; /* FNV-1a over 32-bit words */
}

/* every attribute of the custom cluster goes through here: the hash covers id, type, access and position */
static void note_attr(uint16_t id, uint8_t type, uint8_t access)
{
    mix(((uint32_t)id << 16) | ((uint32_t)type << 8) | access);
    if ((access & ESP_ZB_ZCL_ATTR_ACCESS_REPORTING) && rep_count < sizeof rep_ids / sizeof rep_ids[0]) {
        rep_ids[rep_count++] = id;
    }
}

static esp_zb_attribute_list_t *custom_cluster(void)
{
    attr_set_hash = 2166136261u;
    esp_zb_attribute_list_t *c = esp_zb_zcl_attr_list_create(MC_CLUSTER_ID);
    const uint8_t R = ESP_ZB_ZCL_ATTR_ACCESS_READ_ONLY, REP = ESP_ZB_ZCL_ATTR_ACCESS_READ_ONLY | ESP_ZB_ZCL_ATTR_ACCESS_REPORTING;
    const uint8_t RW = ESP_ZB_ZCL_ATTR_ACCESS_READ_WRITE;
#define ADD(id, type, acc, ptr) \
    note_attr((id), (type), (acc)); \
    ESP_ERROR_CHECK(esp_zb_cluster_add_manufacturer_attr(c, MC_CLUSTER_ID, (id), MANUF, (type), (acc), (ptr)))
    ADD(MC_ATTR_SEQ, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.seq);
    ADD(MC_ATTR_BOOT_ID, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.boot_id);
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        ADD(MC_ATTR_SLOT_0 + i, ESP_ZB_ZCL_ATTR_TYPE_OCTET_STRING, REP, store.slot[i]);
    }
    ADD(MC_ATTR_STATUS, ESP_ZB_ZCL_ATTR_TYPE_8BIT_ENUM, REP, &store.status);
    ADD(MC_ATTR_FAST_MODE, ESP_ZB_ZCL_ATTR_TYPE_U8, REP, &store.fast_mode);
    ADD(MC_ATTR_SAFE_REASON, ESP_ZB_ZCL_ATTR_TYPE_8BIT_ENUM, REP, &store.safe_reason);
    ADD(MC_ATTR_UPTIME_S, ESP_ZB_ZCL_ATTR_TYPE_U32, REP, &store.uptime_s);
    ADD(MC_ATTR_BOOT_REASON, ESP_ZB_ZCL_ATTR_TYPE_8BIT_ENUM, REP, &store.boot_reason);
    ADD(MC_ATTR_RESET_COUNT, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.reset_count);
    ADD(MC_ATTR_REJOIN_COUNT, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.rejoin_count);
    ADD(MC_ATTR_LAST_ERROR, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.last_error);
    ADD(MC_ATTR_FREE_HEAP, ESP_ZB_ZCL_ATTR_TYPE_U32, REP, &store.free_heap);
    ADD(MC_ATTR_INTERFACE_VERSION, ESP_ZB_ZCL_ATTR_TYPE_U16, R, &store.interface_version);
    ADD(MC_ATTR_CONFIG_SCHEMA, ESP_ZB_ZCL_ATTR_TYPE_U8, R, &store.config_schema);
    ADD(MC_ATTR_BATT_MV, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.batt_mv);
    ADD(MC_ATTR_BATT_STATE, ESP_ZB_ZCL_ATTR_TYPE_8BIT_ENUM, REP, &store.batt_state);
    ADD(MC_ATTR_BOARD, ESP_ZB_ZCL_ATTR_TYPE_CHAR_STRING, R, store.board);
    ADD(MC_ATTR_CFG_REV, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.cfg_rev);
    ADD(MC_ATTR_CFG_RESULT, ESP_ZB_ZCL_ATTR_TYPE_8BIT_ENUM, REP, &store.cfg_result);
    ADD(MC_ATTR_CFG_ERROR, ESP_ZB_ZCL_ATTR_TYPE_U16, REP, &store.cfg_error);
    ADD(MC_ATTR_REPORT_INTERVAL_S, ESP_ZB_ZCL_ATTR_TYPE_U16, RW, &store.report_interval_s);
    ADD(MC_ATTR_FAST_REPORT_INTERVAL_S, ESP_ZB_ZCL_ATTR_TYPE_U16, RW, &store.fast_report_interval_s);
    ADD(MC_ATTR_FAST_REPORT_HOLD_S, ESP_ZB_ZCL_ATTR_TYPE_U16, RW, &store.fast_report_hold_s);
    ADD(MC_ATTR_BATT_LOW_MV, ESP_ZB_ZCL_ATTR_TYPE_U16, RW, &store.batt_low_mv);
    ADD(MC_ATTR_BATT_CRITICAL_MV, ESP_ZB_ZCL_ATTR_TYPE_U16, RW, &store.batt_critical_mv);
    ADD(MC_ATTR_BATT_CAL_PERMILLE, ESP_ZB_ZCL_ATTR_TYPE_U16, RW, &store.batt_cal_permille);
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        ADD(MC_ATTR_SLOT_CFG_0 + i, ESP_ZB_ZCL_ATTR_TYPE_OCTET_STRING, RW, store.slot_cfg[i]);
    }
#undef ADD
#define X(id, min_s, max_s, change) mix(((uint32_t)(id) << 16) ^ ((uint32_t)(min_s) << 8) ^ (uint32_t)(max_s) ^ ((uint32_t)(change) << 24));
    MC_REPORTING_LIST(X)
#undef X
    return c;
}

static void zstr(uint8_t *dst, const char *s, size_t cap)
{
    size_t n = strlen(s);
    if (n > cap) {
        n = cap;
    }
    dst[0] = (uint8_t)n;
    memcpy(dst + 1, s, n);
}

static void register_endpoint(void)
{
    store.interface_version = MC_INTERFACE_VERSION;
    store.config_schema = MC_CONFIG_SCHEMA;
    store.report_interval_s = MC_CFG_REPORT_INTERVAL_S_DEFAULT;
    store.fast_report_interval_s = MC_CFG_FAST_REPORT_INTERVAL_S_DEFAULT;
    store.fast_report_hold_s = MC_CFG_FAST_REPORT_HOLD_S_DEFAULT;
    store.batt_low_mv = MC_CFG_BATT_LOW_MV_DEFAULT;
    store.batt_critical_mv = MC_CFG_BATT_CRITICAL_MV_DEFAULT;
    store.batt_cal_permille = MC_CFG_BATT_CAL_PERMILLE_DEFAULT;
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        store.slot[i][0] = 8;
        store.slot_cfg[i][0] = 0;
    }
    zstr(store.board, have_factory ? factory_copy.board : "", 16);

    uint8_t manufacturer[24], model[12], sw[8];
    zstr(manufacturer, MC_MANUFACTURER, 20);
    zstr(model, MC_MODEL, 10);
    zstr(sw, "0.1.0", 6);

    esp_zb_cluster_list_t *list = esp_zb_zcl_cluster_list_create();
    esp_zb_basic_cluster_cfg_t basic_cfg = {.zcl_version = ESP_ZB_ZCL_BASIC_ZCL_VERSION_DEFAULT_VALUE,
                                            .power_source = 0x01 /* mains */};
    esp_zb_attribute_list_t *basic = esp_zb_basic_cluster_create(&basic_cfg);
    ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic, ESP_ZB_ZCL_ATTR_BASIC_MANUFACTURER_NAME_ID, manufacturer));
    ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic, ESP_ZB_ZCL_ATTR_BASIC_MODEL_IDENTIFIER_ID, model));
    ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic, ESP_ZB_ZCL_ATTR_BASIC_SW_BUILD_ID, sw));
    ESP_ERROR_CHECK(esp_zb_cluster_list_add_basic_cluster(list, basic, SRV));

    esp_zb_identify_cluster_cfg_t identify_cfg = {.identify_time = 0};
    ESP_ERROR_CHECK(esp_zb_cluster_list_add_identify_cluster(list, esp_zb_identify_cluster_create(&identify_cfg), SRV));

    esp_zb_power_config_cluster_cfg_t power_cfg = {0};
    esp_zb_attribute_list_t *power = esp_zb_power_config_cluster_create(&power_cfg);
    /* added by hand: the helper creates it without the reporting flag, which Zigbee2MQTT's configure needs */
    ESP_ERROR_CHECK(esp_zb_cluster_add_attr(power, ESP_ZB_ZCL_CLUSTER_ID_POWER_CONFIG, ESP_ZB_ZCL_ATTR_POWER_CONFIG_BATTERY_VOLTAGE_ID,
                                            ESP_ZB_ZCL_ATTR_TYPE_U8,
                                            ESP_ZB_ZCL_ATTR_ACCESS_READ_ONLY | ESP_ZB_ZCL_ATTR_ACCESS_REPORTING, &store.batt_100mv));
    ESP_ERROR_CHECK(esp_zb_cluster_list_add_power_config_cluster(list, power, SRV));

    ESP_ERROR_CHECK(esp_zb_cluster_list_add_custom_cluster(list, custom_cluster(), SRV));

    esp_zb_ep_list_t *eps = esp_zb_ep_list_create();
    esp_zb_endpoint_config_t ep = {.endpoint = EP,
                                   .app_profile_id = ESP_ZB_AF_HA_PROFILE_ID,
                                   .app_device_id = ESP_ZB_HA_CUSTOM_ATTR_DEVICE_ID,
                                   .app_device_version = 0};
    ESP_ERROR_CHECK(esp_zb_ep_list_add_ep(eps, list, ep));
    ESP_ERROR_CHECK(esp_zb_device_register(eps));
}

/* ---- incoming: attribute writes and cluster commands (Zigbee task) ------------------------------------- */

static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint16_t rd16(const uint8_t *p)
{
    return (uint16_t)(p[0] | (p[1] << 8));
}

static esp_err_t on_set_attr(const esp_zb_zcl_set_attr_value_message_t *m)
{
    if (m->info.status != ESP_ZB_ZCL_STATUS_SUCCESS || m->info.cluster != MC_CLUSTER_ID) {
        return ESP_OK;
    }
    mc_event_t ev = {.kind = MC_EV_ZB_ATTR_WRITE};
    ev.u.write.attr = m->attribute.id;
    const uint8_t *v = m->attribute.data.value;
    if (m->attribute.data.type == ESP_ZB_ZCL_ATTR_TYPE_OCTET_STRING) {
        uint8_t n = v[0];
        if (n > sizeof ev.u.write.data) {
            n = sizeof ev.u.write.data;
        }
        memcpy(ev.u.write.data, v + 1, n);
        ev.u.write.len = n;
    } else {
        uint8_t n = m->attribute.data.size > sizeof ev.u.write.data ? sizeof ev.u.write.data : (uint8_t)m->attribute.data.size;
        memcpy(ev.u.write.data, v, n);
        ev.u.write.len = n;
    }
    post(&ev);
    return ESP_OK;
}

static esp_err_t on_custom_cmd(const esp_zb_zcl_custom_cluster_command_message_t *m)
{
    if (m->info.cluster != MC_CLUSTER_ID) {
        return ESP_OK;
    }
    const uint8_t *d = m->data.value;
    uint16_t n = m->data.size;
    mc_event_t ev = {.kind = MC_EV_ZB_CMD};
    mc_cmd_t *c = &ev.u.cmd;
    switch (m->info.command.id) {
    case MC_CMD_IN_COMMIT_CONFIG:
        if (n < 2) {
            return ESP_ERR_INVALID_SIZE;
        }
        c->kind = MC_CMD_COMMIT_CONFIG;
        c->rev = rd16(d);
        break;
    case MC_CMD_IN_PUMP_RUN:
        if (n < 9) {
            return ESP_ERR_INVALID_SIZE;
        }
        c->kind = MC_CMD_PUMP_RUN;
        c->cmd_id = rd32(d);
        c->slot = d[4];
        c->seconds = rd16(d + 5);
        c->ttl_s = rd16(d + 7);
        break;
    case MC_CMD_IN_PUMP_STOP:
        if (n < 5) {
            return ESP_ERR_INVALID_SIZE;
        }
        c->kind = MC_CMD_PUMP_STOP;
        c->cmd_id = rd32(d);
        c->slot = d[4];
        break;
    case MC_CMD_IN_CANCEL:
        if (n < 8) {
            return ESP_ERR_INVALID_SIZE;
        }
        c->kind = MC_CMD_CANCEL;
        c->cmd_id = rd32(d);
        c->target = rd32(d + 4);
        break;
    case MC_CMD_IN_DEVICE_ACTION:
        if (n < 7) {
            return ESP_ERR_INVALID_SIZE;
        }
        c->kind = MC_CMD_DEVICE_ACTION;
        c->cmd_id = rd32(d);
        c->action = d[4];
        c->arg = rd16(d + 5);
        break;
    default:
        return ESP_ERR_NOT_SUPPORTED;
    }
    post(&ev);
    return ESP_OK;
}

static esp_err_t core_action(esp_zb_core_action_callback_id_t id, const void *message)
{
    switch (id) {
    case ESP_ZB_CORE_SET_ATTR_VALUE_CB_ID:
        return on_set_attr(message);
    case ESP_ZB_CORE_CMD_CUSTOM_CLUSTER_REQ_CB_ID:
        return on_custom_cmd(message);
    default:
        return ESP_OK;
    }
}

/* ---- network signals ------------------------------------------------------------------------------------- */

static void poll_configured(uint8_t unused)
{
    (void)unused;
    esp_zb_zcl_attr_location_info_t loc = {.endpoint_id = EP,
                                           .cluster_id = MC_CLUSTER_ID,
                                           .cluster_role = SRV,
                                           .manuf_code = MANUF,
                                           .attr_id = MC_ATTR_STATUS};
    esp_zb_zcl_reporting_info_t *r = esp_zb_zcl_find_reporting_info(loc);
    if (r != NULL && r->u.send_info.max_interval != 0) {
        join_seen_configured = true;
        post_simple(MC_EV_ZB_CONFIGURED);
    } else if (++configure_polls < 60) {
        esp_zb_scheduler_alarm(poll_configured, 0, 2000); /* until the core's interview timeout ends it anyway */
    }
}

static void begin_configure_watch(void)
{
    join_seen_configured = false;
    configure_polls = 0;
    esp_zb_scheduler_alarm(poll_configured, 0, 2000);
}

static void start_commissioning(uint8_t mode)
{
    if (esp_zb_bdb_start_top_level_commissioning(mode) != ESP_OK) {
        ESP_LOGE(TAG, "starting commissioning mode %u failed", mode);
    }
}

/* ---- reporting records after a change of the attribute set -------------------------------------------------- */

/* The stack keeps its reporting records in `zb_storage`, matched to the attributes by position. A firmware that adds,
 * removes or re-orders attributes (or changes the reporting table) then aborts at the first report. So the module
 * remembers a hash of what it registered; when it differs, it throws the stored records away and sets up its own
 * from interface.yaml. The network, the bindings and the settings stay. */
#define NVS_NS "mc_zb"
#define NVS_KEY_HASH "attr_hash"

static bool attr_set_changed(void)
{
    nvs_handle_t h;
    uint32_t stored = 0;
    if (nvs_open(NVS_NS, NVS_READONLY, &h) != ESP_OK) {
        return true; /* never stored: a firmware from before this check, or a fresh module */
    }
    bool same = nvs_get_u32(h, NVS_KEY_HASH, &stored) == ESP_OK && stored == attr_set_hash;
    nvs_close(h);
    return !same;
}

static void remember_attr_set(void)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NS, NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_u32(h, NVS_KEY_HASH, attr_set_hash);
        nvs_commit(h);
        nvs_close(h);
    }
}

static void table_values(uint16_t id, uint16_t *min_s, uint16_t *max_s, uint16_t *change)
{
    *min_s = 0;
    *max_s = 0xFFFF; /* the module sends these itself (octet strings cannot be configured, seq and boot_id are explicit) */
    *change = 0;
#define X(aid, mn, mx, ch) \
    if (id == (aid)) { \
        *min_s = (mn); \
        *max_s = (mx); \
        *change = (ch); \
    }
    MC_REPORTING_LIST(X)
#undef X
}

static void rebuild_reporting(void)
{
    esp_zb_zcl_reset_all_reporting_info();
    for (size_t i = 0; i < rep_count; i++) {
        esp_zb_zcl_reporting_info_t info = {0};
        uint16_t change;
        info.direction = ESP_ZB_ZCL_REPORT_DIRECTION_SEND;
        info.ep = EP;
        info.cluster_id = MC_CLUSTER_ID;
        info.cluster_role = SRV;
        info.attr_id = rep_ids[i];
        info.manuf_code = MANUF;
        table_values(rep_ids[i], &info.u.send_info.min_interval, &info.u.send_info.max_interval, &change);
        info.u.send_info.def_min_interval = info.u.send_info.min_interval;
        info.u.send_info.def_max_interval = info.u.send_info.max_interval;
        info.u.send_info.delta.u16 = change;
        info.dst.profile_id = ESP_ZB_AF_HA_PROFILE_ID;
        esp_err_t e = esp_zb_zcl_update_reporting_info(&info);
        if (e != ESP_OK) {
            ESP_LOGW(TAG, "reporting record for 0x%04x: %s", rep_ids[i], esp_err_to_name(e));
        }
    }
    esp_zb_zcl_reporting_info_t power = {0};
    power.direction = ESP_ZB_ZCL_REPORT_DIRECTION_SEND;
    power.ep = EP;
    power.cluster_id = ESP_ZB_ZCL_CLUSTER_ID_POWER_CONFIG;
    power.cluster_role = SRV;
    power.attr_id = ESP_ZB_ZCL_ATTR_POWER_CONFIG_BATTERY_VOLTAGE_ID;
    power.u.send_info.min_interval = power.u.send_info.def_min_interval = MC_REPORTING_POWER_MIN_S;
    power.u.send_info.max_interval = power.u.send_info.def_max_interval = MC_REPORTING_POWER_MAX_S;
    power.u.send_info.delta.u8 = MC_REPORTING_POWER_CHANGE;
    power.dst.profile_id = ESP_ZB_AF_HA_PROFILE_ID;
    esp_zb_zcl_update_reporting_info(&power);
    ESP_LOGW(TAG, "attribute set changed: reporting records rebuilt (hash 0x%08x)", (unsigned)attr_set_hash);
}

/* The network state is known: bring the reporting records in line with the attribute set, then let the app use the stack. */
static void stack_started(bool joined)
{
    if (reporting_stale) {
        if (joined) {
            rebuild_reporting();
        }
        remember_attr_set(); /* a module without a network has no records to be stale */
        reporting_stale = false;
    }
    stack_up = true;
}

void esp_zb_app_signal_handler(esp_zb_app_signal_t *signal_struct)
{
    uint32_t *p = signal_struct->p_app_signal;
    esp_err_t status = signal_struct->esp_err_status;
    esp_zb_app_signal_type_t type = *p;
    ESP_LOGI(TAG, "signal %s (0x%x): %s", esp_zb_zdo_signal_to_string(type), (unsigned)type, esp_err_to_name(status));
    switch (type) {
    case ESP_ZB_ZDO_SIGNAL_SKIP_STARTUP:
        reporting_stale = attr_set_changed();
        start_commissioning(ESP_ZB_BDB_MODE_INITIALIZATION);
        break;
    case ESP_ZB_BDB_SIGNAL_DEVICE_FIRST_START:
    case ESP_ZB_BDB_SIGNAL_DEVICE_REBOOT:
        if (status == ESP_OK) {
            bool joined = !esp_zb_bdb_is_factory_new();
            ESP_LOGI(TAG, "stack ready, %s", joined ? "joined" : "factory new");
            stack_started(joined);
            mc_event_t ev = {.kind = MC_EV_ZB_STACK_READY};
            ev.u.joined = joined;
            post(&ev);
        } else if (type == ESP_ZB_BDB_SIGNAL_DEVICE_REBOOT && !esp_zb_bdb_is_factory_new()) {
            /* The network was restored from flash but the parent did not answer (coordinator off or away): the
             * module is joined without a link, which is the rejoin back-off of the core, not a start failure. */
            ESP_LOGW(TAG, "network restored, parent not reachable");
            stack_started(true);
            mc_event_t ev = {.kind = MC_EV_ZB_STACK_READY};
            ev.u.joined = true;
            post(&ev);
            post_simple(MC_EV_ZB_PARENT_LOST);
        } else {
            ESP_LOGE(TAG, "stack start failed: %s", esp_err_to_name(status));
        }
        break;
    case ESP_ZB_BDB_SIGNAL_STEERING:
        if (status == ESP_OK) {
            ESP_LOGI(TAG, "%s network 0x%04x channel %u", rejoining ? "rejoined" : "joined", esp_zb_get_pan_id(),
                     esp_zb_get_current_channel());
            if (rejoining) {
                rejoining = false;
                post_bool(MC_EV_ZB_REJOIN_DONE, true);
            } else {
                post_simple(MC_EV_ZB_JOINED);
                begin_configure_watch();
            }
        } else {
            ESP_LOGW(TAG, "steering failed: %s", esp_err_to_name(status));
            if (rejoining) {
                rejoining = false;
                post_bool(MC_EV_ZB_REJOIN_DONE, false);
            } else {
                post_bool(MC_EV_ZB_STEERING_DONE, false);
            }
        }
        break;
    case ESP_ZB_NWK_SIGNAL_NO_ACTIVE_LINKS_LEFT:
        ESP_LOGW(TAG, "parent lost");
        post_simple(MC_EV_ZB_PARENT_LOST);
        break;
    case ESP_ZB_ZDO_SIGNAL_LEAVE: {
        esp_zb_zdo_signal_leave_params_t *lp = esp_zb_app_signal_get_params(p);
        ESP_LOGW(TAG, "left the network (type %u)", lp ? lp->leave_type : 255);
        post_simple(MC_EV_ZB_LEFT);
        break;
    }
    default:
        break;
    }
}

/* ---- the Zigbee task --------------------------------------------------------------------------------------- */

static void zb_task(void *arg)
{
    (void)arg;
    esp_zb_cfg_t cfg = {
        .esp_zb_role = ESP_ZB_DEVICE_TYPE_ED,
        .install_code_policy = have_factory && factory_copy.install_code_required && !params.dev_join,
        .nwk_cfg.zed_cfg = {.ed_timeout = ESP_ZB_ED_AGING_TIMEOUT_64MIN, .keep_alive = 3000},
    };
    esp_zb_init(&cfg);
    esp_zb_set_rx_on_when_idle(true); /* the receiver stays on: PlantModule/specs.md 8 */
    if (have_factory && factory_copy.has_install_code) {
        uint8_t ic[18];
        memcpy(ic, factory_copy.install_code, 16);
        uint16_t crc = mc_crc16_x25(ic, 16);
        ic[16] = (uint8_t)(crc & 0xFF);
        ic[17] = (uint8_t)(crc >> 8);
        ESP_ERROR_CHECK(esp_zb_secur_ic_set(ESP_ZB_IC_TYPE_128, ic));
    }
    register_endpoint();
    esp_zb_core_action_handler_register(core_action);
    esp_zb_set_primary_network_channel_set(ESP_ZB_TRANSCEIVER_ALL_CHANNELS_MASK);
    ESP_ERROR_CHECK(esp_zb_start(false));
    esp_zb_set_tx_power(CONFIG_MC_ZB_TX_POWER);
    esp_zb_stack_main_loop();
}

/* ---- the actions of the core ------------------------------------------------------------------------------- */

void mc_zb_start(const mc_zb_params_t *p)
{
    params = *p;
    have_factory = p->factory != NULL;
    if (have_factory) {
        factory_copy = *p->factory;
    }
    esp_zb_platform_config_t platform = {
        .radio_config = {.radio_mode = ZB_RADIO_MODE_NATIVE},
        .host_config = {.host_connection_mode = ZB_HOST_CONNECTION_MODE_NONE},
    };
    ESP_ERROR_CHECK(esp_zb_platform_config(&platform));
    xTaskCreate(zb_task, "zigbee", 6144, NULL, 5, NULL);
}

void mc_zb_start_steering(void)
{
    rejoining = false;
    if (esp_zb_lock_acquire(pdMS_TO_TICKS(1000))) {
        start_commissioning(ESP_ZB_BDB_MODE_NETWORK_STEERING);
        esp_zb_lock_release();
    }
}

void mc_zb_rejoin(void)
{
    rejoining = true;
    if (esp_zb_lock_acquire(pdMS_TO_TICKS(1000))) {
        start_commissioning(ESP_ZB_BDB_MODE_NETWORK_STEERING);
        esp_zb_lock_release();
    }
}

void mc_zb_leave(void)
{
    if (esp_zb_lock_acquire(pdMS_TO_TICKS(1000))) {
        esp_zb_bdb_reset_via_local_action();
        esp_zb_lock_release();
    }
}

static void set_attr(uint16_t id, void *value)
{
    esp_zb_zcl_status_t s = esp_zb_zcl_set_manufacturer_attribute_val(EP, MC_CLUSTER_ID, SRV, MANUF, id, value, false);
    if (s != ESP_ZB_ZCL_STATUS_SUCCESS) {
        ESP_LOGW(TAG, "setting attribute 0x%04x failed (%d)", id, s);
    }
}

void mc_zb_update_attrs(const mc_attrs_t *a)
{
    store.seq = a->seq;
    store.boot_id = a->boot_id;
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        store.slot[i][0] = 8;
        mc_encode_slot_reading(&a->readings[i], store.slot[i] + 1);
    }
    store.status = a->status;
    store.fast_mode = a->fast_mode;
    store.safe_reason = a->safe_reason;
    store.uptime_s = (uint32_t)(esp_timer_get_time() / 1000000);
    store.boot_reason = a->boot_reason;
    store.reset_count = a->reset_count;
    store.rejoin_count = a->rejoin_count;
    store.last_error = a->last_error;
    store.free_heap = (uint32_t)esp_get_free_heap_size();
    store.cfg_rev = a->cfg_rev;
    store.cfg_result = a->cfg_result;
    store.cfg_error = a->cfg_error;
    store.batt_100mv = (uint8_t)(a->voltage_mv / 100);
    store.batt_mv = a->voltage_mv;
    store.batt_state = a->batt_state;

    if (!stack_up || !esp_zb_lock_acquire(pdMS_TO_TICKS(1000))) { /* the stack reads `store` itself once it is up */
        return;
    }
    set_attr(MC_ATTR_SEQ, &store.seq);
    set_attr(MC_ATTR_BOOT_ID, &store.boot_id);
    for (int i = 0; i < MC_NUM_SLOTS; i++) {
        set_attr(MC_ATTR_SLOT_0 + i, store.slot[i]);
    }
    set_attr(MC_ATTR_STATUS, &store.status);
    set_attr(MC_ATTR_FAST_MODE, &store.fast_mode);
    set_attr(MC_ATTR_SAFE_REASON, &store.safe_reason);
    set_attr(MC_ATTR_UPTIME_S, &store.uptime_s);
    set_attr(MC_ATTR_BOOT_REASON, &store.boot_reason);
    set_attr(MC_ATTR_RESET_COUNT, &store.reset_count);
    set_attr(MC_ATTR_REJOIN_COUNT, &store.rejoin_count);
    set_attr(MC_ATTR_LAST_ERROR, &store.last_error);
    set_attr(MC_ATTR_FREE_HEAP, &store.free_heap);
    set_attr(MC_ATTR_CFG_REV, &store.cfg_rev);
    set_attr(MC_ATTR_CFG_RESULT, &store.cfg_result);
    set_attr(MC_ATTR_CFG_ERROR, &store.cfg_error);
    set_attr(MC_ATTR_BATT_MV, &store.batt_mv);
    set_attr(MC_ATTR_BATT_STATE, &store.batt_state);
    esp_zb_zcl_set_attribute_val(EP, ESP_ZB_ZCL_CLUSTER_ID_POWER_CONFIG, SRV, ESP_ZB_ZCL_ATTR_POWER_CONFIG_BATTERY_VOLTAGE_ID,
                                 &store.batt_100mv, false);
    esp_zb_lock_release();
}

static esp_err_t report_attr(uint16_t cluster, uint16_t attr, uint16_t manuf)
{
    esp_zb_zcl_report_attr_cmd_t cmd = {0};
    cmd.zcl_basic_cmd.src_endpoint = EP;
    cmd.address_mode = ESP_ZB_APS_ADDR_MODE_DST_ADDR_ENDP_NOT_PRESENT; /* through the binding Zigbee2MQTT made */
    cmd.clusterID = cluster;
    cmd.attributeID = attr;
    cmd.direction = ESP_ZB_ZCL_CMD_DIRECTION_TO_CLI;
    if (manuf) {
        cmd.manuf_specific = 1;
        cmd.manuf_code = manuf;
    }
    return esp_zb_zcl_report_attr_cmd_req(&cmd);
}

void mc_zb_report_now(void)
{
    if (!stack_up || !esp_zb_lock_acquire(pdMS_TO_TICKS(1000))) {
        post_bool(MC_EV_ZB_REPORT_RESULT, false);
        return;
    }
    /* Zigbee2MQTT publishes its accumulated state after every attribute, and the hub takes a new `seq` as "a new
     * reading": `seq` goes last, so the state that carries it already holds the new slots and status. */
    static const uint16_t attrs[] = {MC_ATTR_SLOT_0,  MC_ATTR_SLOT_1,   MC_ATTR_SLOT_2,     MC_ATTR_SLOT_3,
                                     MC_ATTR_SLOT_4,  MC_ATTR_SLOT_5,   MC_ATTR_STATUS,     MC_ATTR_FAST_MODE,
                                     MC_ATTR_BATT_MV, MC_ATTR_BATT_STATE, MC_ATTR_CFG_REV, MC_ATTR_CFG_RESULT,
                                     MC_ATTR_CFG_ERROR, MC_ATTR_SEQ};
    bool ok = true;
    for (size_t i = 0; i < sizeof attrs / sizeof attrs[0]; i++) {
        ok &= report_attr(MC_CLUSTER_ID, attrs[i], MANUF) == ESP_OK;
    }
    esp_zb_lock_release();
    post_bool(MC_EV_ZB_REPORT_RESULT, ok);
}

static void send_custom(uint8_t cmd_id, const uint8_t *data, uint16_t len)
{
    esp_zb_zcl_custom_cluster_cmd_req_t req = {0};
    req.zcl_basic_cmd.src_endpoint = EP;
    req.zcl_basic_cmd.dst_endpoint = 1;
    req.address_mode = ESP_ZB_APS_ADDR_MODE_DST_ADDR_ENDP_NOT_PRESENT;
    req.profile_id = ESP_ZB_AF_HA_PROFILE_ID;
    req.cluster_id = MC_CLUSTER_ID;
    req.manuf_specific = 1;
    req.manuf_code = MANUF;
    req.direction = ESP_ZB_ZCL_CMD_DIRECTION_TO_CLI;
    req.custom_cmd_id = cmd_id;
    req.data.type = ESP_ZB_ZCL_ATTR_TYPE_SET;
    req.data.size = len;
    req.data.value = (void *)data;
    if (esp_zb_lock_acquire(pdMS_TO_TICKS(1000))) {
        esp_zb_zcl_custom_cluster_cmd_req(&req);
        esp_zb_lock_release();
    }
}

static void put16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

void mc_zb_send_ack(uint16_t n, uint32_t cmd_id, uint8_t state, uint8_t reason, uint16_t ends_in_s)
{
    uint8_t b[10];
    put16(b, n);
    b[2] = (uint8_t)cmd_id;
    b[3] = (uint8_t)(cmd_id >> 8);
    b[4] = (uint8_t)(cmd_id >> 16);
    b[5] = (uint8_t)(cmd_id >> 24);
    b[6] = state;
    b[7] = reason;
    put16(b + 8, ends_in_s);
    send_custom(MC_CMD_OUT_CMD_ACK, b, sizeof b);
}

void mc_zb_send_event(uint16_t n, uint8_t code, uint8_t slot, uint16_t arg)
{
    uint8_t b[6];
    put16(b, n);
    b[2] = code;
    b[3] = slot;
    put16(b + 4, arg);
    send_custom(MC_CMD_OUT_EVENT, b, sizeof b);
}
