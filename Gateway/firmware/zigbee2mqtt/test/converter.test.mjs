import assert from 'node:assert/strict';
import fs from 'node:fs';
import {test} from 'node:test';
import {fileURLToPath} from 'node:url';

import {addExternalDefinition, findByDevice} from 'zigbee-herdsman-converters';

import {
  MANUFACTURER_CODE, Zcl, applyFromZigbee, clusterDefinition, commandBytes, customClusters, definition, I,
  receiveCommand, receiveReport, recordingEndpoint, slotBytes, toZigbeeFor,
} from './helpers.mjs';

const fixtureFile = (name) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

/** Compares with a committed fixture (the hub's tests read the same file); UPDATE_FIXTURES=1 rewrites it. */
function checkFixture(name, actual) {
  const file = fixtureFile(name);
  if (process.env.UPDATE_FIXTURES) fs.writeFileSync(file, `${JSON.stringify(actual, null, 2)}\n`);
  assert.deepEqual(actual, JSON.parse(fs.readFileSync(file, 'utf8')), `${name} is out of date (UPDATE_FIXTURES=1 rewrites it)`);
}

const T = Zcl.DataType;

// ---- the definition as Zigbee2MQTT loads it ---------------------------------------------------------

test('Zigbee2MQTT finds the definition for the module and rejects look-alikes', async () => {
  addExternalDefinition(definition);
  const device = (modelID, manufacturerName) => ({modelID, manufacturerName, ieeeAddr: '0x00124b0001', type: 'EndDevice', endpoints: [], customClusters: {}});
  const found = await findByDevice(device('MC-PLANT', 'MoistureController'));
  assert.equal(found.model, 'MC-PLANT');
  assert.equal(found.vendor, 'MoistureController');
  assert.ok(found.exposes.length > 20, 'exposes are prepared');
  assert.ok(found.fromZigbee.length >= 4 && found.toZigbee.length >= 5);
  const other = await findByDevice(device('TS0601', '_TZE200_x'));
  assert.notEqual(other?.model, 'MC-PLANT');
});

test('the custom cluster covers every attribute and command of the interface', () => {
  assert.equal(clusterDefinition.ID, 0xfc11);
  assert.equal(clusterDefinition.manufacturerCode, MANUFACTURER_CODE);
  for (const a of I.attributes) {
    const d = clusterDefinition.attributes[a.name];
    assert.ok(d, `attribute ${a.name}`);
    assert.equal(d.ID, a.id);
    assert.equal(Boolean(d.write), a.access.includes('rw'), `${a.name} writable`);
  }
  assert.deepEqual(Object.keys(clusterDefinition.commands), ['commitConfig', 'pumpRun', 'pumpStop', 'cancel', 'deviceAction']);
  assert.deepEqual(Object.keys(clusterDefinition.commandsResponse), ['cmdAck', 'event']);
});

// ---- module -> hub, through herdsman's frame parser ------------------------------------------------------

test('a full report becomes the state of the specification', () => {
  const msg = receiveReport({
    seq: [T.UINT16, 1042],
    boot_id: [T.UINT16, 7],
    slot_0: [T.OCTET_STR, slotBytes({type: 1, value: 4150, raw: 2143})],
    slot_2: [T.OCTET_STR, slotBytes({type: 2, value: 0, raw: 0})],
    status: [T.ENUM8, 0],
    fast_mode: [T.UINT8, 0],
    safe_reason: [T.ENUM8, 0],
    cfg_rev: [T.UINT16, 8],
    cfg_result: [T.ENUM8, 0],
    cfg_error: [T.UINT16, 0],
    uptime_s: [T.UINT32, 86400],
    boot_reason: [T.ENUM8, 0],
    reset_count: [T.UINT16, 0],
    rejoin_count: [T.UINT16, 1],
    last_error: [T.UINT16, 0],
    free_heap: [T.UINT32, 143000],
    interface_version: [T.UINT16, 0x0100],
    config_schema: [T.UINT8, 1],
    board: [T.CHAR_STR, 'carrier-v1'],
  });
  const state = applyFromZigbee(definition, msg);
  assert.deepEqual(state, {
    seq: 1042, boot_id: 7,
    slot0_type: 'moisture', slot0_value: 41.5, slot0_raw: 2143, slot0_error: 'ok',
    slot2_type: 'pump', slot2_value: 0, slot2_raw: 0, slot2_error: 'ok',
    status: 'operational', fast_mode: false, safe_reason: 'none',
    cfg_rev: 8, cfg_result: 'ok', cfg_error: null,
    uptime_s: 86400, boot_reason: 'power_on', reset_count: 0, rejoin_count: 1, last_error: 0, free_heap: 143000,
    interface: '1.0', config_schema: 1, board: 'carrier-v1',
  });
  checkFixture('module_report.json', state);
});

test('a read response is converted like a report', () => {
  const msg = receiveReport({board: [T.CHAR_STR, 'devkitc-1']});
  assert.deepEqual(applyFromZigbee(definition, {...msg, type: 'readResponse'}), {board: 'devkitc-1'});
});

test('cmd_ack and event arrive as transient objects with their counters', () => {
  const ack = applyFromZigbee(definition, receiveCommand('cmdAck', {n: 17, cmd_id: 1048577, state: 1, reason: 0, ends_in_s: 0}));
  assert.deepEqual(ack, {cmd_ack: {n: 17, cmd_id: 1048577, state: 'done', reason: 'none', ends_in_s: 0}});
  const running = applyFromZigbee(definition, receiveCommand('cmdAck', {n: 16, cmd_id: 1048577, state: 0, reason: 0, ends_in_s: 10}));
  assert.equal(running.cmd_ack.state, 'running');
  assert.equal(running.cmd_ack.ends_in_s, 10);
  const event = applyFromZigbee(definition, receiveCommand('event', {n: 4, code: 3, slot: 1, arg: 0}));
  assert.deepEqual(event, {event: {n: 4, code: 'sensor_fault', slot: 1, arg: 0}});
  checkFixture('module_commands.json', {ack, running, event});
});

test('the supply voltage of the Power Configuration cluster is informational', () => {
  const state = applyFromZigbee(definition, {cluster: 'genPowerCfg', type: 'attributeReport', data: {batteryVoltage: 50}, meta: {}});
  assert.deepEqual(state, {voltage_mv: 5000});
  assert.deepEqual(applyFromZigbee(definition, {cluster: 'genPowerCfg', type: 'attributeReport', data: {batteryPercentageRemaining: 10}, meta: {}}), {});
});

// ---- hub -> module ------------------------------------------------------------------------------------------

const HUB_SET = JSON.parse(fs.readFileSync(fixtureFile('hub_set_payloads.json'), 'utf8'));

async function runSet(payload) {
  const ep = recordingEndpoint();
  for (const [key, value] of Object.entries(payload)) {
    await toZigbeeFor(definition, key).convertSet(ep, key, value, {message: payload});
  }
  return ep.calls;
}

test('config: the writable attributes first, then commit_config with the revision', async () => {
  const calls = await runSet(HUB_SET.config);
  const commit = calls[calls.length - 1];
  const writes = calls.slice(0, -1);
  assert.ok(writes.length >= 2, 'the configuration does not fit in one frame');
  for (const w of writes) {
    assert.equal(w.op, 'write');
    assert.equal(w.cluster, 'mcPlant');
    assert.deepEqual(w.options, {manufacturerCode: MANUFACTURER_CODE});
    assert.ok(Object.keys(w.attributes).length <= 12, 'a write stays small');
  }
  const write = {attributes: Object.assign({}, ...writes.map((w) => w.attributes))};
  assert.deepEqual(Object.keys(write.attributes), [
    'report_interval_s', 'fast_report_interval_s', 'fast_report_hold_s', 'batt_low_mv', 'batt_critical_mv', 'batt_cal_permille', 'power_mode', 'poll_interval_ms', 'awake_s',
    'slot_cfg_0', 'slot_cfg_1', 'slot_cfg_2', 'slot_cfg_3', 'slot_cfg_4', 'slot_cfg_5',
  ]);
  for (const name of Object.keys(write.attributes)) {
    assert.ok(clusterDefinition.attributes[name].write, `${name} is writable`);
  }
  assert.equal(write.attributes.report_interval_s, 300);
  assert.deepEqual([...write.attributes.slot_cfg_0], [1, 0, 0, 0xb8, 0x0b, 0xb0, 0x04, 16]);
  assert.deepEqual([...write.attributes.slot_cfg_2], [2, 2, 1, 60, 0, 0x58, 0x02]);
  assert.deepEqual({op: commit.op, command: commit.command, payload: commit.payload}, {op: 'command', command: 'commitConfig', payload: {rev: 9}});
});

test('an invalid config sends nothing', async () => {
  const ep = recordingEndpoint();
  await assert.rejects(toZigbeeFor(definition, 'config').convertSet(ep, 'config', {rev: 3, report_interval_s: 5}), /report_interval_s/);
  await assert.rejects(toZigbeeFor(definition, 'config').convertSet(ep, 'config', {report_interval_s: 300}), /rev/);
  assert.deepEqual(ep.calls, []);
});

test('pump_run, pump_stop and cancel: one cluster command with the interface parameters', async () => {
  const run = (await runSet(HUB_SET.pump_run))[0];
  assert.deepEqual({cluster: run.cluster, command: run.command, payload: run.payload, options: run.options}, {
    cluster: 'mcPlant', command: 'pumpRun',
    payload: {cmd_id: 1048577, slot: 2, seconds: 10, ttl_s: 900}, options: {manufacturerCode: MANUFACTURER_CODE},
  });
  assert.equal((await runSet(HUB_SET.pump_stop))[0].command, 'pumpStop');
  assert.deepEqual((await runSet(HUB_SET.pump_stop))[0].payload, {cmd_id: 1048578, slot: 2});
  assert.deepEqual((await runSet(HUB_SET.cancel))[0].payload, {cmd_id: 1048579, target: 1048577});
});

test('device_action: the action name becomes the enum value', async () => {
  const call = (await runSet(HUB_SET.device_action))[0];
  assert.equal(call.command, 'deviceAction');
  assert.deepEqual(call.payload, {cmd_id: 1048580, action: 1, arg: 0});
  const reboot = (await runSet({device_action: {cmd_id: 7, action: 'reboot'}}))[0];
  assert.equal(reboot.payload.action, 2);
  await assert.rejects(runSet({device_action: {cmd_id: 7, action: 'format'}}), /not one of/);
});

test('the cluster commands have the byte layout of the interface', () => {
  // frame control (manufacturer specific, cluster specific, client to server), manufacturer code, tsn, command id, fields
  const run = commandBytes('pumpRun', {cmd_id: 0x00100001, slot: 2, seconds: 10, ttl_s: 900});
  assert.deepEqual([...run.subarray(0, 1)].map((x) => x & 0b111), [0b101]); // frame type specific + manufacturer specific flag
  assert.deepEqual([...run.subarray(1, 3)], [MANUFACTURER_CODE & 0xff, MANUFACTURER_CODE >> 8]);
  assert.equal(run[4], 0x01); // pump_run
  assert.deepEqual([...run.subarray(5)], [0x01, 0x00, 0x10, 0x00, 2, 10, 0, 0x84, 0x03]); // cmd_id u32, slot u8, seconds u16, ttl u16
  assert.equal(commandBytes('pumpStop', {cmd_id: 1, slot: 2})[4], 0x02);
  assert.equal(commandBytes('cancel', {cmd_id: 1, target: 2})[4], 0x03);
  assert.equal(commandBytes('deviceAction', {cmd_id: 1, action: 1, arg: 0})[4], 0x04);
  assert.deepEqual([...commandBytes('commitConfig', {rev: 9}).subarray(4)], [0x00, 9, 0]);
});

// ---- joining ---------------------------------------------------------------------------------------------------

test('configure binds the clusters and sets the reporting of the interface', async () => {
  const ep = recordingEndpoint();
  const device = {getEndpoint: (id) => (id === I.identity.endpoint ? ep : undefined)};
  const coordinator = {ID: 1};
  await definition.configure(device, coordinator, definition);
  const binds = ep.calls.filter((c) => c.op === 'bind').map((c) => c.cluster);
  assert.deepEqual(binds, ['mcPlant', 'genPowerCfg']);
  const customCalls = ep.calls.filter((c) => c.op === 'configureReporting' && c.cluster === 'mcPlant');
  assert.ok(customCalls.every((c) => c.items.length <= 6), 'a configure command must fit in one frame');
  const configured = customCalls.flatMap((c) => c.items.map((i) => i.attribute));
  for (const name of ['status', 'cfg_rev', 'cfg_error', 'uptime_s', 'free_heap']) {
    assert.ok(configured.includes(name), `${name} is reported`);
    assert.ok(clusterDefinition.attributes[name], `${name} exists in the cluster`);
  }
  assert.ok(!configured.some((n) => n.startsWith('slot_')), 'slot readings are sent by the module, the stack cannot report octet strings');
  assert.deepEqual(customCalls.flatMap((c) => c.items).find((i) => i.attribute === 'status'), {attribute: 'status', minimumReportInterval: 1, maximumReportInterval: 600, reportableChange: 0});
  assert.ok(customCalls.every((c) => c.options.manufacturerCode === MANUFACTURER_CODE));
  const read = ep.calls.find((c) => c.op === 'read');
  assert.deepEqual(read.attributes, ['board', 'interface_version', 'config_schema'], 'the board is read once: it is not reportable');
  const power = ep.calls.find((c) => c.op === 'configureReporting' && c.cluster === 'genPowerCfg');
  assert.deepEqual(power.items[0], {attribute: 'batteryVoltage', minimumReportInterval: 60, maximumReportInterval: 600, reportableChange: 1});
});
