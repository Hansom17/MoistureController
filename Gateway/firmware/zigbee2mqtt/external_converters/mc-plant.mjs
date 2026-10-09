// Zigbee2MQTT external converter for the PlantModule (PlantModule/specs.md Part B, interface.yaml).
//
// Reports and commands of the module become the state JSON the hub expects on `zigbee2mqtt/<dev-id>`
// (Gateway/specs.md 7.5); the hub's `set` keys become attribute writes and cluster commands.
// The attribute and command tables come from `mc-plant/interface.mjs`, generated from interface.yaml.
import {Zcl} from 'zigbee-herdsman';
import * as exposes from 'zigbee-herdsman-converters/lib/exposes';
import * as m from 'zigbee-herdsman-converters/lib/modernExtend';

import * as codec from './mc-plant/codec.mjs';
import I from './mc-plant/interface.mjs';

const e = exposes.presets;
const ea = exposes.access;

const CLUSTER = 'mcPlant';
const OPTS = {manufacturerCode: I.cluster.manufacturerCode};

const DATA_TYPE = {
  uint8: Zcl.DataType.UINT8,
  uint16: Zcl.DataType.UINT16,
  uint32: Zcl.DataType.UINT32,
  int16: Zcl.DataType.INT16,
  enum8: Zcl.DataType.ENUM8,
  char16: Zcl.DataType.CHAR_STR,
  octet6: Zcl.DataType.OCTET_STR,
  octet8: Zcl.DataType.OCTET_STR,
  octet24: Zcl.DataType.OCTET_STR,
};

const commandDefinition = (c) => ({
  ID: c.id,
  name: c.name,
  parameters: c.fields.map((f) => ({name: f.name, type: DATA_TYPE[f.type]})),
});

/** The custom cluster 0xFC11 as herdsman wants it. */
export const clusterDefinition = {
  name: CLUSTER,
  ID: I.cluster.id,
  manufacturerCode: I.cluster.manufacturerCode,
  attributes: Object.fromEntries(
    I.attributes.map((a) => [
      a.name,
      {name: a.name, ID: a.id, type: DATA_TYPE[a.type], ...(a.access.includes('rw') ? {write: true} : {})},
    ]),
  ),
  commands: Object.fromEntries(I.commandsIn.map((c) => [c.name, commandDefinition(c)])),
  commandsResponse: Object.fromEntries(I.commandsOut.map((c) => [c.name, commandDefinition(c)])),
};

// ---- module -> hub ---------------------------------------------------------------------------------

const fzAttributes = {
  cluster: CLUSTER,
  type: ['attributeReport', 'readResponse'],
  convert: (model, msg) => codec.attributesToState(msg.data),
};

const fzCmdAck = {
  cluster: CLUSTER,
  type: ['commandCmdAck'],
  convert: (model, msg) => ({cmd_ack: codec.decodeCmdAck(msg.data)}),
};

const fzEvent = {
  cluster: CLUSTER,
  type: ['commandEvent'],
  convert: (model, msg) => ({event: codec.decodeEvent(msg.data)}),
};

/** The supply voltage in 100 mV units; informational while the module is powered externally. */
const fzVoltage = {
  cluster: 'genPowerCfg',
  type: ['attributeReport', 'readResponse'],
  convert: (model, msg) => (msg.data.batteryVoltage === undefined ? undefined : {voltage_mv: msg.data.batteryVoltage * 100}),
};

// ---- hub -> module ---------------------------------------------------------------------------------

/** One hub `set` key = one cluster command with the parameters named as in the interface. */
const commandConverter = (c) => ({
  key: [c.mqtt],
  convertSet: async (entity, key, value) => {
    const payload = {...value};
    if (c.mqtt === 'device_action') payload.action = codec.encodeDeviceAction(value.action);
    if (c.mqtt === 'device_action' && payload.arg === undefined) payload.arg = 0;
    await entity.command(CLUSTER, c.name, payload, OPTS);
  },
});

/** `config`: the writable attributes (staged on the module), then `commit_config(rev)` applies them. */
const tzConfig = {
  key: ['config'],
  convertSet: async (entity, key, value) => {
    const rev = value.rev;
    if (!Number.isInteger(rev) || rev < 0 || rev > 65535) throw new Error(`config.rev must be 0..65535, got ${rev}`);
    await entity.write(CLUSTER, codec.encodeConfig(value), OPTS);
    await entity.command(CLUSTER, 'commitConfig', {rev}, OPTS);
  },
};

// ---- exposes -----------------------------------------------------------------------------------------

const enumValues = (id) => Object.values(I.enums[id]);

function buildExposes() {
  const out = [];
  for (let n = 0; n < 6; n++) {
    out.push(e.numeric(`slot${n}_value`, ea.STATE).withUnit('%').withDescription(`Slot ${n + 1}: moisture in %, or the pump output (100 = on)`));
    out.push(e.enum(`slot${n}_type`, ea.STATE, enumValues('module')).withDescription(`Slot ${n + 1}: module`));
    out.push(e.enum(`slot${n}_error`, ea.STATE, enumValues('sensor_error')).withDescription(`Slot ${n + 1}: sensor state`));
  }
  out.push(e.enum('status', ea.STATE, enumValues('status')));
  out.push(e.enum('safe_reason', ea.STATE, enumValues('safe_reason')));
  out.push(e.binary('fast_mode', ea.STATE, true, false).withDescription('Reporting fast while watering'));
  out.push(e.numeric('seq', ea.STATE).withDescription('Sample counter'));
  out.push(e.numeric('cfg_rev', ea.STATE).withDescription('Configuration revision the module runs'));
  out.push(e.enum('cfg_result', ea.STATE, enumValues('cfg_result')));
  out.push(e.text('cfg_error', ea.STATE));
  out.push(e.numeric('voltage_mv', ea.STATE).withUnit('mV'));
  for (const [name, unit] of [['uptime_s', 's'], ['reset_count', null], ['rejoin_count', null], ['last_error', null], ['free_heap', 'B']]) {
    const x = e.numeric(name, ea.STATE).withCategory('diagnostic');
    out.push(unit ? x.withUnit(unit) : x);
  }
  out.push(e.enum('boot_reason', ea.STATE, enumValues('boot_reason')).withCategory('diagnostic'));
  out.push(e.text('board', ea.STATE).withCategory('diagnostic'));
  out.push(e.text('interface', ea.STATE).withCategory('diagnostic'));
  return out;
}

// ---- reporting ---------------------------------------------------------------------------------------

/** What `configure` sets up, from the `reporting` table of the interface. */
export function reportingPlan() {
  const custom = [];
  let power = null;
  for (const r of I.reporting) {
    for (const attr of r.attributes) {
      if (attr.startsWith('power_config.')) {
        power = {attribute: attr.split('.')[1], minimumReportInterval: r.min_s, maximumReportInterval: r.max_s, reportableChange: 1};
      } else {
        // octet strings and enums are reported whole: a change threshold only applies to analog values
        custom.push({attribute: attr, minimumReportInterval: r.min_s, maximumReportInterval: r.max_s, reportableChange: 0});
      }
    }
  }
  return {custom, power};
}

async function configure(device, coordinatorEndpoint) {
  const endpoint = device.getEndpoint(I.identity.endpoint);
  await endpoint.bind(CLUSTER, coordinatorEndpoint);
  await endpoint.bind('genPowerCfg', coordinatorEndpoint);
  const {custom, power} = reportingPlan();
  await endpoint.configureReporting(CLUSTER, custom, OPTS);
  if (power) await endpoint.configureReporting('genPowerCfg', [power]);
}

export default {
  fingerprint: [{modelID: I.identity.model, manufacturerName: I.identity.manufacturer}],
  zigbeeModel: [I.identity.model],
  model: I.identity.model,
  vendor: I.identity.manufacturer,
  description: 'Plant module: soil moisture sensors and a pump (always-awake Zigbee end device)',
  extend: [m.deviceAddCustomCluster(CLUSTER, clusterDefinition)],
  fromZigbee: [fzAttributes, fzCmdAck, fzEvent, fzVoltage],
  toZigbee: [tzConfig, ...I.commandsIn.filter((c) => c.mqtt && c.mqtt !== 'config').map(commandConverter)],
  exposes: buildExposes(),
  configure,
};
