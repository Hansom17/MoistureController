#include "mc_json.h"

static void put(struct mc_jw *w, char c)
{
	if (w->len + 1 < w->cap) {
		w->buf[w->len] = c;
	} else {
		w->overflow = true;
	}
	w->len++;
}

static void puts_raw(struct mc_jw *w, const char *s)
{
	while (*s) {
		put(w, *s++);
	}
}

static void put_u64(struct mc_jw *w, uint64_t v)
{
	char tmp[20];
	int n = 0;

	do {
		tmp[n++] = (char)('0' + v % 10);
		v /= 10;
	} while (v);
	while (n) {
		put(w, tmp[--n]);
	}
}

/* Separator before a value (or a key). */
static void before_value(struct mc_jw *w)
{
	if (w->after_key) {
		w->after_key = false;
	} else if (w->need_comma) {
		put(w, ',');
	}
}

void mc_jw_init(struct mc_jw *w, char *buf, size_t cap)
{
	w->buf = buf;
	w->cap = cap;
	w->len = 0;
	w->overflow = false;
	w->need_comma = false;
	w->after_key = false;
}

void mc_jw_obj(struct mc_jw *w)
{
	before_value(w);
	put(w, '{');
	w->need_comma = false;
}

void mc_jw_end_obj(struct mc_jw *w)
{
	put(w, '}');
	w->need_comma = true;
}

void mc_jw_arr(struct mc_jw *w)
{
	before_value(w);
	put(w, '[');
	w->need_comma = false;
}

void mc_jw_end_arr(struct mc_jw *w)
{
	put(w, ']');
	w->need_comma = true;
}

static void put_string(struct mc_jw *w, const char *s)
{
	static const char hex[] = "0123456789abcdef";

	put(w, '"');
	for (; *s; s++) {
		unsigned char c = (unsigned char)*s;

		if (c == '"' || c == '\\') {
			put(w, '\\');
			put(w, (char)c);
		} else if (c < 0x20) {
			puts_raw(w, "\\u00");
			put(w, hex[c >> 4]);
			put(w, hex[c & 15]);
		} else {
			put(w, (char)c); /* UTF-8 passes through */
		}
	}
	put(w, '"');
}

void mc_jw_key(struct mc_jw *w, const char *key)
{
	before_value(w);
	put_string(w, key);
	put(w, ':');
	w->after_key = true;
}

void mc_jw_int(struct mc_jw *w, int64_t v)
{
	before_value(w);
	if (v < 0) {
		put(w, '-');
		put_u64(w, (uint64_t)0 - (uint64_t)v);
	} else {
		put_u64(w, (uint64_t)v);
	}
	w->need_comma = true;
}

void mc_jw_str(struct mc_jw *w, const char *s)
{
	before_value(w);
	put_string(w, s);
	w->need_comma = true;
}

void mc_jw_bool(struct mc_jw *w, bool v)
{
	before_value(w);
	puts_raw(w, v ? "true" : "false");
	w->need_comma = true;
}

void mc_jw_dec1(struct mc_jw *w, int32_t tenths)
{
	uint32_t a = tenths < 0 ? (uint32_t)(-(int64_t)tenths) : (uint32_t)tenths;

	before_value(w);
	if (tenths < 0) {
		put(w, '-');
	}
	put_u64(w, a / 10);
	put(w, '.');
	put(w, (char)('0' + a % 10));
	w->need_comma = true;
}

void mc_jw_kv_int(struct mc_jw *w, const char *key, int64_t v)
{
	mc_jw_key(w, key);
	mc_jw_int(w, v);
}

void mc_jw_kv_str(struct mc_jw *w, const char *key, const char *s)
{
	mc_jw_key(w, key);
	mc_jw_str(w, s);
}

void mc_jw_kv_bool(struct mc_jw *w, const char *key, bool v)
{
	mc_jw_key(w, key);
	mc_jw_bool(w, v);
}

int mc_jw_finish(struct mc_jw *w)
{
	if (w->overflow || w->cap == 0) {
		if (w->cap) {
			w->buf[w->cap - 1] = '\0';
		}
		return -1;
	}
	w->buf[w->len] = '\0';
	return (int)w->len;
}
