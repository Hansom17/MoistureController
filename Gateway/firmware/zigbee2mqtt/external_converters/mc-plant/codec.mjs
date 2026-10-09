// Encoding and decoding of the PlantModule's custom cluster (PlantModule/interface.yaml).
// Pure functions without any Zigbee2MQTT dependency, so they are tested on their own.
import I from './interface.mjs';

export const UNKNOWN_VALUE = -32768; // 0x8000: "no value"

const ATTR_BY_NAME = Object.fromEntries(I.attributes.map((a) => [a.name, a]));

const enumName = (enumId, n) => I.enums[enumId]?.[String(n)] ?? `unknown_${n}`;
const enumValue = (enumId, name) => {
  const hit = Object.entries(I.enums[enumId]).find(([, v]) => v === name);
  if (!hit) throw new Error(`${name} is not one of ${Object.values(I.enums[enumId]).join(', ')}`);
  return Number(hit[0]);
};

/** Buffer, number array or Uint8Array -> Buffer. */
export const toBuffer = (v) => (Buffer.isBuffer(v) ? v : Buffer.from(v));

// ---- device -> hub ---------------------------------------------------------------------------------

/** Attribute `slot_n`, 8 bytes: type u8, error u8, value i16 (% x 100), raw u16, cfg_rev u16. */
export function decodeSlot(value) {
  const b = toBuffer(value);
  if (b.length < 8) throw new Error(`slot reading needs 8 bytes, got ${b.length}`);
  const v = b.readInt16LE(2);
  return {
    type: enumName('module', b.readUInt8(0)),
    error: enumName('sensor_error', b.readUInt8(1)),
    value: v === UNKNOWN_VALUE ? null : v / 100,
    raw: b.readUInt16LE(4),
    cfg_rev: b.readUInt16LE(6),
  };
}

/** `cfg_error`: high byte = error code, low byte = slot (0xFF = the device as a whole); 0 = none. */
export function decodeCfgError(n) {
  if (!n) return null;
  const code = enumName('cfg_error', n >> 8);
  const slot = n & 0xff;
  return slot === 0xff ? code : `${code} (slot ${slot + 1})`;
}

export function decodeInterfaceVersion(n) {
  return `${n >> 8}.${n & 0xff}`;
}

/** Zero-terminated or padded character string -> text. */
export function decodeText(v) {
  return (typeof v === 'string' ? v : toBuffer(v).toString('utf8')).replace(/\0+$/, '');
}

/**
 * The attributes of one report or read response (keyed by attribute name, as herdsman gives them) as
 * the flat state the hub expects: `slot0_type`, `slot0_value`, ..., `seq`, `status`, `cfg_error`, ...
 */
export function attributesToState(data) {
  const out = {};
  for (const [name, raw] of Object.entries(data)) {
    const a = ATTR_BY_NAME[name];
    if (!a?.mqtt) continue;
    if (a.layout === 'slot_reading') {
      const n = a.name.slice('slot_'.length);
      const s = decodeSlot(raw);
      out[`slot${n}_type`] = s.type;
      out[`slot${n}_value`] = s.value;
      out[`slot${n}_raw`] = s.raw;
      out[`slot${n}_error`] = s.error;
    } else if (a.name === 'cfg_error') {
      out[a.mqtt] = decodeCfgError(raw);
    } else if (a.name === 'interface_version') {
      out[a.mqtt] = decodeInterfaceVersion(raw);
    } else if (a.name === 'fast_mode') {
      out[a.mqtt] = Boolean(raw);
    } else if (a.type === 'char16') {
      out[a.mqtt] = decodeText(raw);
    } else if (a.enum) {
      out[a.mqtt] = enumName(a.enum, raw);
    } else {
      out[a.mqtt] = raw;
    }
  }
  return out;
}

/** Command `cmd_ack` from the module. */
export function decodeCmdAck(d) {
  return {
    n: d.n,
    cmd_id: d.cmd_id,
    state: enumName('ack_state', d.state),
    reason: enumName('reason', d.reason),
    ends_in_s: d.ends_in_s,
  };
}

/** Command `event` from the module. */
export function decodeEvent(d) {
  return { n: d.n, code: enumName('event_code', d.code), slot: d.slot, arg: d.arg };
}

// ---- hub -> device ---------------------------------------------------------------------------------

const intIn = (v, name, lo, hi) => {
  if (!Number.isInteger(v) || v < lo || v > hi) throw new Error(`${name} must be an integer ${lo}..${hi}, got ${v}`);
  return v;
};

/** "P1".."P6" -> 0..5; "GPIO5" -> 0x85 (only for boards that allow raw GPIOs). */
export function encodePort(port) {
  const m = /^P([1-6])$/.exec(port);
  if (m) return Number(m[1]) - 1;
  const g = /^GPIO(\d{1,2})$/.exec(port);
  if (g) return 0x80 + intIn(Number(g[1]), 'gpio', 0, 40);
  throw new Error(`port must be P1..P6 or GPIO<n>, got ${port}`);
}

/** Attribute `slot_cfg_n`: module u8, port u8, flags u8 (bit 0: active high), then the parameters of the module. */
export function encodeSlotConfig(slot) {
  if (!slot || slot.module === 'empty') return Buffer.from([0, 0, 0]);
  const module = enumValue('module', slot.module);
  const port = encodePort(slot.port);
  if (slot.module === 'moisture') {
    const b = Buffer.alloc(8);
    b.writeUInt8(module, 0);
    b.writeUInt8(port, 1);
    b.writeUInt8(0, 2);
    b.writeUInt16LE(intIn(slot.cal_dry ?? 3000, 'cal_dry', 0, 65535), 3);
    b.writeUInt16LE(intIn(slot.cal_wet ?? 1200, 'cal_wet', 0, 65535), 5);
    b.writeUInt8(intIn(slot.samples ?? 16, 'samples', 1, 255), 7);
    return b;
  }
  if (slot.module === 'pump') {
    const b = Buffer.alloc(7);
    b.writeUInt8(module, 0);
    b.writeUInt8(port, 1);
    b.writeUInt8(slot.active_high === false ? 0 : 1, 2);
    b.writeUInt16LE(intIn(slot.max_run_s ?? 60, 'max_run_s', 1, 65535), 3);
    b.writeUInt16LE(intIn(slot.min_pause_s ?? 600, 'min_pause_s', 0, 65535), 5);
    return b;
  }
  throw new Error(`unknown module ${slot.module}`);
}

/**
 * The configuration of the hub's `config` message as the attribute writes of the cluster:
 * the intervals and all six slot tables (slots not mentioned are emptied).
 */
export function encodeConfig(config) {
  const slots = config.slots ?? [];
  const bySlot = new Map();
  for (const s of slots) {
    const n = intIn(s.slot, 'slot', 0, 5);
    if (bySlot.has(n)) throw new Error(`slot ${n} appears twice`);
    bySlot.set(n, s);
  }
  const attrs = {
    report_interval_s: intIn(config.report_interval_s ?? 300, 'report_interval_s', 10, 3600),
    fast_report_interval_s: intIn(config.fast_report_interval_s ?? 30, 'fast_report_interval_s', 10, 300),
    fast_report_hold_s: intIn(config.fast_report_hold_s ?? 120, 'fast_report_hold_s', 0, 1800),
    batt_low_mv: intIn(config.batt_low_mv ?? 3500, 'batt_low_mv', 0, 65535),
  };
  for (let n = 0; n < 6; n++) attrs[`slot_cfg_${n}`] = encodeSlotConfig(bySlot.get(n));
  return attrs;
}

/** `device_action` of the hub -> enum value of the command. */
export const encodeDeviceAction = (name) => enumValue('device_action', name);
