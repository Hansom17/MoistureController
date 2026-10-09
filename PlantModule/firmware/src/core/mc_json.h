/* Minimal compact-JSON writer into a fixed buffer (mqtt.md §9: compact, UTF-8). */
#ifndef MC_JSON_H
#define MC_JSON_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct mc_jw {
	char *buf;
	size_t cap;
	size_t len;
	bool overflow;
	bool need_comma;
	bool after_key;
};

void mc_jw_init(struct mc_jw *w, char *buf, size_t cap);
void mc_jw_obj(struct mc_jw *w);
void mc_jw_end_obj(struct mc_jw *w);
void mc_jw_arr(struct mc_jw *w);
void mc_jw_end_arr(struct mc_jw *w);
void mc_jw_key(struct mc_jw *w, const char *key);
void mc_jw_int(struct mc_jw *w, int64_t v);
void mc_jw_str(struct mc_jw *w, const char *s);
void mc_jw_bool(struct mc_jw *w, bool v);
/* A number with one decimal from tenths, e.g. 415 -> 41.5 (no floats on the wire path). */
void mc_jw_dec1(struct mc_jw *w, int32_t tenths);

void mc_jw_kv_int(struct mc_jw *w, const char *key, int64_t v);
void mc_jw_kv_str(struct mc_jw *w, const char *key, const char *s);
void mc_jw_kv_bool(struct mc_jw *w, const char *key, bool v);

/* NUL-terminates; returns the length, or -1 if the buffer was too small. */
int mc_jw_finish(struct mc_jw *w);

#endif /* MC_JSON_H */
