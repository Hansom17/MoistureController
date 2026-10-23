#ifndef MC_APP_H
#define MC_APP_H

#include <stdbool.h>

#include "mc_core.h"
#include "mc_factory.h"

/* Starts the application task, which owns mc_core_t and all hardware access. */
void mc_app_start(const mc_board_t *board, const mc_factory_t *factory, bool factory_valid);

#endif
