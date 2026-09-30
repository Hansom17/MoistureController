/*
 * Commands (mqtt.md §5): parsing, duplicate history, and the decision what to do with
 * each one. Pure logic: the caller executes hardware actions and keeps the state in
 * retained memory across deep sleep.
 */
#ifndef MC_CMD_H
#define MC_CMD_H

#include "mc_config.h"
#include "mc_defs.h"
#include "mc_json.h"

enum mc_action {
	MC_ACT_UNKNOWN,
	MC_ACT_PUMP_RUN,
	MC_ACT_PUMP_STOP,
	MC_ACT_CMD_CANCEL,
	MC_ACT_DEVICE_IDENTIFY,
	MC_ACT_DEVICE_SERVICE,
	MC_ACT_DEVICE_REBOOT,
};

struct mc_cmd {
	char id[MC_ID_LEN + 1];
	enum mc_action action;
	int64_t exp;
	int32_t slot;           /* -1 = not given */
	int32_t seconds;        /* -1 = not given */
	int32_t minutes;        /* -1 = not given */
	char target[MC_ID_LEN + 1];
};

/* mqtt.md §5.3 */
enum mc_ack_status { MC_ACK_RUNNING, MC_ACK_DONE, MC_ACK_REJECTED, MC_ACK_FAILED,
		     MC_ACK_CANCELLED };

struct mc_ack {
	char id[MC_ID_LEN + 1];
	enum mc_ack_status status;
	char reason[20];        /* §8.2, for rejected / failed; "" = none (no pointers: lives in RTC RAM) */
	int64_t ts;             /* done; 0 = omit */
	int64_t ends_at;        /* running; 0 = omit */
};

const char *mc_ack_status_name(enum mc_ack_status s);

/* Parses a cmd payload (modifies `buf`). False if it isn't a command at all (no usable id). */
bool mc_cmd_parse(char *buf, size_t len, struct mc_cmd *out);

/* --- last commands, for duplicate delivery (§5.2) ------------------------------------------ */

struct mc_cmd_hist {
	struct mc_ack e[MC_CMD_HISTORY]; /* the ack carries the command id; "" = free */
	uint8_t next;           /* slot to overwrite next */
};

void mc_hist_init(struct mc_cmd_hist *h);
const struct mc_ack *mc_hist_find(const struct mc_cmd_hist *h, const char *id);
/* Stores or updates the ack for `id` (a `running` command later gets its final ack). */
void mc_hist_put(struct mc_cmd_hist *h, const char *id, const struct mc_ack *ack);

/* --- pump state (kept in retained memory) ---------------------------------------------------- */

struct mc_pump_state {
	int64_t last_end;       /* when the last run ended; 0 = never */
	int64_t run_ends_at;    /* > 0: a run is holding through sleep until then */
	char run_cmd[MC_ID_LEN + 1];
};

/* --- decisions --------------------------------------------------------------------------------- */

enum mc_do_kind { MC_DO_NONE, MC_DO_PUMP_RUN, MC_DO_PUMP_STOP, MC_DO_IDENTIFY, MC_DO_SERVICE,
		  MC_DO_REBOOT };

struct mc_outcome {
	struct mc_ack ack;      /* final, or `rejected`; for DO_* it is the ack to send once done */
	enum mc_do_kind action; /* what the caller must execute, if anything */
	int32_t slot;
	int32_t value;          /* seconds / minutes */
	bool duplicate;         /* a repeated command: only re-send `ack` */
};

struct mc_ctx {
	const struct mc_config *cfg;
	int64_t now;            /* Unix seconds; only meaningful if time_synced */
	bool time_synced;
	struct mc_pump_state pump[MC_SLOTS_MAX];
	struct mc_cmd_hist *hist;
};

/*
 * Decides one command. Does not execute anything; `pump[]` and `hist` are only read
 * (callers record the final ack with mc_hist_put()).
 */
void mc_cmd_decide(const struct mc_ctx *ctx, const struct mc_cmd *cmd, struct mc_outcome *out);

/*
 * Processes the commands the broker delivered in one wake, in order, honouring
 * `cmd.cancel` for commands of the same batch that haven't run yet (§5.1):
 * the target is acked `cancelled`, the cancel itself `done`. A cancel for a command
 * not seen yet leaves a tombstone in the history so it is `cancelled` when it arrives.
 *
 * `cb` is called for every command in execution order with its outcome; it must
 * execute `out->action` (filling out->ack if needed) and return; the ack it leaves in
 * out->ack is recorded in the history by this function.
 */
typedef void (*mc_cmd_exec_fn)(struct mc_ctx *ctx, const struct mc_cmd *cmd,
			       struct mc_outcome *out, void *user);

void mc_cmd_process(struct mc_ctx *ctx, const struct mc_cmd *cmds, size_t n,
		    mc_cmd_exec_fn cb, void *user);

/* --- pump run planning ---------------------------------------------------------------------------- */

/* Runs up to this long are carried out within the wake window; longer ones hold through sleep. */
#define MC_PUMP_INLINE_MAX_S 15

bool mc_pump_run_is_inline(int32_t seconds);

/* Records a run that continues through deep sleep (§5.2 "Long runs"). */
void mc_pump_begin_hold(struct mc_pump_state *p, const char *cmd_id, int64_t ends_at);
/* Records the end of a run that was completed within the wake window. */
void mc_pump_finish(struct mc_pump_state *p, int64_t now);

/*
 * At wake: a held run whose time has come must be switched off now.
 * Returns the slot to switch off or -1.
 */
int mc_pump_due_stop(const struct mc_ctx *ctx);

/* Seconds until the device must wake for a held run's end; -1 if none. */
int32_t mc_pump_next_stop_in(const struct mc_ctx *ctx);

/*
 * Ends a held run on this pump (it was stopped, or its time has come): records the end,
 * and if a command is attached to the run fills `ack` with `status` for it and returns true.
 */
bool mc_pump_end_hold(struct mc_pump_state *p, int64_t now, enum mc_ack_status status,
		      struct mc_ack *ack);

/* Commands handled per wake; more are left for the next cycle by the caller. */
#define MC_CMD_BATCH_MAX 16

#endif /* MC_CMD_H */
