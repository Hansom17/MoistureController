#ifndef MC_ZIGBEE_H
#define MC_ZIGBEE_H

/* The Zigbee side of the module. The implementation runs the esp-zigbee-sdk in its own task and talks to the
 * application only through mc_app_post() events (STACK_READY, STEERING_DONE, JOINED, CONFIGURED, PARENT_LOST,
 * REJOIN_DONE, LEFT, ATTR_WRITE, CMD, REPORT_RESULT). The functions below are the actions of the core. */

#include <stdbool.h>
#include <stdint.h>

#include "mc_core.h"
#include "mc_factory.h"

typedef struct {
    const mc_factory_t *factory; /* install code and serial; NULL without factory data */
    bool dev_join;               /* CONFIG_MC_DEV_JOIN: may join with the default link key */
} mc_zb_params_t;

void mc_zb_start(const mc_zb_params_t *params); /* posts STACK_READY{joined} */
void mc_zb_start_steering(void);                /* posts STEERING_DONE / JOINED */
void mc_zb_rejoin(void);                        /* posts REJOIN_DONE */
void mc_zb_leave(void);                         /* leaves and erases the network state; posts LEFT */

/* The attribute store and the reporting. `attrs` also carries what the core knows; the implementation adds
 * uptime and free heap itself. */
void mc_zb_update_attrs(const mc_attrs_t *attrs);
void mc_zb_report_now(void);
void mc_zb_send_ack(uint16_t n, uint32_t cmd_id, uint8_t state, uint8_t reason, uint16_t ends_in_s);
void mc_zb_send_event(uint16_t n, uint8_t code, uint8_t slot, uint16_t arg);

#endif
