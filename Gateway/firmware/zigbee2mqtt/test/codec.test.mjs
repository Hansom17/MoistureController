import assert from 'node:assert/strict';
import {test} from 'node:test';

import * as codec from '../external_converters/mc-plant/codec.mjs';

test('slot reading: a moisture value', () => {
  const b = Buffer.from([1, 0, 0x16, 0x10, 0x5f, 0x08, 0x08, 0x00]);
  assert.deepEqual(codec.decodeSlot(b), {type: 'moisture', error: 'ok', value: 41.18, raw: 2143, cfg_rev: 8});
});

test('slot reading: unknown value, sensor errors and pump state', () => {
  const unknown = Buffer.from([1, 1, 0x00, 0x80, 0, 0, 0, 0]);
  assert.deepEqual(codec.decodeSlot(unknown), {type: 'moisture', error: 'no_signal', value: null, raw: 0, cfg_rev: 0});
  assert.equal(codec.decodeSlot([2, 0, 0x10, 0x27, 0, 0, 1, 0]).value, 100); // pump on = 100
  assert.equal(codec.decodeSlot([2, 0, 0, 0, 0, 0, 1, 0]).value, 0);
  assert.equal(codec.decodeSlot([1, 0, 0x9c, 0xff, 0, 0, 0, 0]).value, -1); // negative values stay negative
  assert.throws(() => codec.decodeSlot([1, 2, 3]), /8 bytes/);
});

test('config error: code and slot, device level, none', () => {
  assert.equal(codec.decodeCfgError(0), null);
  assert.equal(codec.decodeCfgError((2 << 8) | 2), 'port_conflict (slot 3)');
  assert.equal(codec.decodeCfgError((5 << 8) | 0xff), 'stale_rev');
  assert.equal(codec.decodeCfgError((99 << 8) | 1), 'unknown_99 (slot 2)');
});

test('interface version and text', () => {
  assert.equal(codec.decodeInterfaceVersion(0x0102), '1.2');
  assert.equal(codec.decodeText('carrier-v1\0\0'), 'carrier-v1');
  assert.equal(codec.decodeText(Buffer.from('devkitc-1\0')), 'devkitc-1');
});

test('attributes become the flat state of the hub', () => {
  const state = codec.attributesToState({
    seq: 1042,
    boot_id: 7,
    slot_0: Buffer.from([1, 0, 0x16, 0x10, 0x5f, 0x08, 0x08, 0x00]),
    slot_2: Buffer.from([2, 0, 0, 0, 0, 0, 8, 0]),
    status: 0,
    fast_mode: 1,
    safe_reason: 3,
    cfg_rev: 8,
    cfg_result: 1,
    cfg_error: (1 << 8) | 2,
    boot_reason: 2,
    uptime_s: 86400,
    interface_version: 0x0100,
    config_schema: 1,
    board: 'carrier-v1',
    report_interval_s: 300, // a configuration attribute has no state key
  });
  assert.deepEqual(state, {
    seq: 1042,
    boot_id: 7,
    slot0_type: 'moisture', slot0_value: 41.18, slot0_raw: 2143, slot0_error: 'ok',
    slot2_type: 'pump', slot2_value: 0, slot2_raw: 0, slot2_error: 'ok',
    status: 'operational',
    fast_mode: true,
    safe_reason: 'crash_loop',
    cfg_rev: 8,
    cfg_result: 'rejected',
    cfg_error: 'port_invalid (slot 3)',
    boot_reason: 'panic',
    uptime_s: 86400,
    interface: '1.0',
    config_schema: 1,
    board: 'carrier-v1',
  });
});

test('unknown attributes and attribute ids are ignored', () => {
  assert.deepEqual(codec.attributesToState({4660: 5, nothing: 1}), {});
});

test('cmd_ack and event names', () => {
  assert.deepEqual(codec.decodeCmdAck({n: 17, cmd_id: 1048577, state: 1, reason: 0, ends_in_s: 0}),
    {n: 17, cmd_id: 1048577, state: 'done', reason: 'none', ends_in_s: 0});
  assert.deepEqual(codec.decodeCmdAck({n: 18, cmd_id: 5, state: 3, reason: 4, ends_in_s: 0}).reason, 'min_pause');
  assert.deepEqual(codec.decodeEvent({n: 4, code: 3, slot: 1, arg: 0}), {n: 4, code: 'sensor_fault', slot: 1, arg: 0});
});

test('ports', () => {
  assert.equal(codec.encodePort('P1'), 0);
  assert.equal(codec.encodePort('P6'), 5);
  assert.equal(codec.encodePort('GPIO5'), 0x85);
  assert.throws(() => codec.encodePort('P7'), /port/);
  assert.throws(() => codec.encodePort('3'), /port/);
});

test('slot config tables', () => {
  // module, port, flags, cal_dry, cal_wet, samples
  assert.deepEqual([...codec.encodeSlotConfig({slot: 0, module: 'moisture', port: 'P1', cal_dry: 3000, cal_wet: 1200, samples: 16})],
    [1, 0, 0, 0xb8, 0x0b, 0xb0, 0x04, 16]);
  // module, port, flags (active high), max_run_s, min_pause_s
  assert.deepEqual([...codec.encodeSlotConfig({slot: 2, module: 'pump', port: 'P3', max_run_s: 60, min_pause_s: 600})],
    [2, 2, 1, 60, 0, 0x58, 0x02]);
  assert.deepEqual([...codec.encodeSlotConfig({slot: 2, module: 'pump', port: 'P3', active_high: false})].slice(0, 3), [2, 2, 0]);
  assert.deepEqual([...codec.encodeSlotConfig(undefined)], [0, 0, 0]);
  assert.deepEqual([...codec.encodeSlotConfig({slot: 4, module: 'empty'})], [0, 0, 0]);
  assert.throws(() => codec.encodeSlotConfig({slot: 0, module: 'led', port: 'P1'}), /unknown module|not one of/);
  assert.throws(() => codec.encodeSlotConfig({slot: 0, module: 'pump', port: 'P1', max_run_s: 70000}), /max_run_s/);
  for (let n = 0; n < 6; n++) assert.ok(codec.encodeSlotConfig({slot: n, module: 'moisture', port: 'P1'}).length <= 24);
});

test('battery thresholds: critical must be below low, calibration within 10 %', () => {
  assert.throws(() => codec.encodeConfig({rev: 1, batt_low_mv: 3500, batt_critical_mv: 3500}), /below/);
  assert.throws(() => codec.encodeConfig({rev: 1, batt_cal_permille: 1200}), /batt_cal_permille/);
  assert.throws(() => codec.encodeConfig({rev: 1, batt_low_mv: 2900}), /batt_low_mv/);
  const a = codec.encodeConfig({rev: 1});
  assert.deepEqual([a.batt_low_mv, a.batt_critical_mv, a.batt_cal_permille], [3600, 3400, 1000], 'defaults');
});

test('power settings: always on by default, ranges from the interface file', () => {
  const a = codec.encodeConfig({rev: 1});
  assert.deepEqual([a.power_mode, a.poll_interval_ms, a.awake_s], [0, 3000, 5], 'defaults');
  const b = codec.encodeConfig({rev: 1, power_mode: 2, poll_interval_ms: 1500, awake_s: 12});
  assert.deepEqual([b.power_mode, b.poll_interval_ms, b.awake_s], [2, 1500, 12]);
  assert.throws(() => codec.encodeConfig({rev: 1, power_mode: 3}), /power_mode/);
  assert.throws(() => codec.encodeConfig({rev: 1, poll_interval_ms: 100}), /poll_interval_ms/);
  assert.throws(() => codec.encodeConfig({rev: 1, awake_s: 31}), /awake_s/);
});

test('whole configuration: intervals and six slot tables, absent slots emptied', () => {
  const a = codec.encodeConfig({
    rev: 9, report_interval_s: 120, fast_report_interval_s: 20, fast_report_hold_s: 60, batt_low_mv: 3700, batt_critical_mv: 3450, batt_cal_permille: 1012,
    slots: [{slot: 0, module: 'moisture', port: 'P1'}, {slot: 2, module: 'pump', port: 'P3'}],
  });
  assert.equal(a.report_interval_s, 120);
  assert.equal(a.fast_report_interval_s, 20);
  assert.equal(a.fast_report_hold_s, 60);
  assert.equal(a.batt_low_mv, 3700);
  assert.equal(a.batt_critical_mv, 3450);
  assert.equal(a.batt_cal_permille, 1012);
  assert.deepEqual(Object.keys(a).filter((k) => k.startsWith('slot_cfg_')), ['slot_cfg_0', 'slot_cfg_1', 'slot_cfg_2', 'slot_cfg_3', 'slot_cfg_4', 'slot_cfg_5']);
  assert.equal(a.slot_cfg_0[0], 1);
  assert.deepEqual([...a.slot_cfg_1], [0, 0, 0]);
  assert.equal(a.slot_cfg_2[0], 2);
});

test('configuration limits are enforced before anything is sent', () => {
  assert.throws(() => codec.encodeConfig({report_interval_s: 5}), /report_interval_s/);
  assert.throws(() => codec.encodeConfig({fast_report_interval_s: 301}), /fast_report_interval_s/);
  assert.throws(() => codec.encodeConfig({slots: [{slot: 6, module: 'empty'}]}), /slot/);
  assert.throws(() => codec.encodeConfig({slots: [{slot: 1, module: 'empty'}, {slot: 1, module: 'empty'}]}), /twice/);
  assert.deepEqual(codec.encodeConfig({}).report_interval_s, 300); // defaults
});

test('device actions', () => {
  assert.equal(codec.encodeDeviceAction('identify'), 1);
  assert.equal(codec.encodeDeviceAction('reboot'), 2);
  assert.equal(codec.encodeDeviceAction('clear_safe_mode'), 3);
  assert.equal(codec.encodeDeviceAction('report_now'), 4);
  assert.throws(() => codec.encodeDeviceAction('format'), /not one of/);
});
