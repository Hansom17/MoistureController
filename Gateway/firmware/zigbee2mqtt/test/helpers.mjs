// Shared by the converter tests: drives the converter the way Zigbee2MQTT does, with the real herdsman
// code for frames and custom clusters.
import {Zcl} from 'zigbee-herdsman';

import definition, {clusterDefinition} from '../external_converters/mc-plant.mjs';
import I from '../external_converters/mc-plant/interface.mjs';

export {definition, clusterDefinition, I};
export const customClusters = {mcPlant: clusterDefinition};
export const MANUFACTURER_CODE = I.cluster.manufacturerCode;

/** 8-byte `slot_n` value: type, error, value (% x 100), raw, cfg_rev. */
export function slotBytes({type = 1, error = 0, value = 4150, raw = 2143, cfgRev = 8} = {}) {
  const b = Buffer.alloc(8);
  b.writeUInt8(type, 0);
  b.writeUInt8(error, 1);
  b.writeInt16LE(value, 2);
  b.writeUInt16LE(raw, 4);
  b.writeUInt16LE(cfgRev, 6);
  return b;
}

/** An attribute report as the module would send it, run through herdsman's frame encoder and parser. */
export function receiveReport(attributes) {
  const payload = Object.entries(attributes).map(([name, [dataType, value]]) => ({
    attrId: clusterDefinition.attributes[name].ID,
    dataType,
    attrData: value,
  }));
  const frame = Zcl.Frame.create(
    Zcl.FrameType.GLOBAL, Zcl.Direction.SERVER_TO_CLIENT, true, MANUFACTURER_CODE, 1, 'report', I.cluster.id, payload, customClusters);
  const buffer = frame.toBuffer();
  const parsed = Zcl.Frame.fromBuffer(I.cluster.id, Zcl.Header.fromBuffer(buffer), buffer, customClusters);
  // what herdsman does before it hands the message to Zigbee2MQTT
  const data = {};
  for (const item of parsed.payload) {
    const attr = Zcl.Utils.getClusterAttribute(parsed.cluster, item.attrId, parsed.header.manufacturerCode);
    data[attr ? attr.name : item.attrId] = attr ? Zcl.Utils.processAttributePostRead(attr, item.attrData) : item.attrData;
  }
  return {cluster: 'mcPlant', type: 'attributeReport', data, endpoint: {ID: 1}, meta: {}};
}

/** A cluster command from the module (`cmdAck`, `event`), through herdsman's frame encoder and parser. */
export function receiveCommand(name, fields) {
  const frame = Zcl.Frame.create(
    Zcl.FrameType.SPECIFIC, Zcl.Direction.SERVER_TO_CLIENT, true, MANUFACTURER_CODE, 2, name, I.cluster.id, fields, customClusters);
  const buffer = frame.toBuffer();
  const parsed = Zcl.Frame.fromBuffer(I.cluster.id, Zcl.Header.fromBuffer(buffer), buffer, customClusters);
  return {
    cluster: 'mcPlant',
    type: `command${name[0].toUpperCase()}${name.slice(1)}`,
    data: parsed.payload,
    endpoint: {ID: 1},
    meta: {},
  };
}

/** Zigbee2MQTT's receive path: every converter of the definition that matches cluster and type contributes to the state. */
export function applyFromZigbee(def, msg) {
  let state = {};
  for (const c of def.fromZigbee) {
    if (c.cluster === msg.cluster && c.type.includes(msg.type)) {
      Object.assign(state, c.convert(def, msg, () => {}, {}, msg.meta) ?? {});
    }
  }
  return state;
}

/** An endpoint that records what Zigbee2MQTT would send. */
export function recordingEndpoint() {
  const calls = [];
  return {
    calls,
    write: async (cluster, attributes, options) => calls.push({op: 'write', cluster, attributes, options}),
    command: async (cluster, command, payload, options) => calls.push({op: 'command', cluster, command, payload, options}),
    read: async (cluster, attributes, options) => calls.push({op: 'read', cluster, attributes, options}),
    bind: async (cluster, target) => calls.push({op: 'bind', cluster, target}),
    configureReporting: async (cluster, items, options) => calls.push({op: 'configureReporting', cluster, items, options}),
  };
}

/** The converter for a `set` key. */
export const toZigbeeFor = (def, key) => def.toZigbee.find((c) => c.key.includes(key));

/** The bytes herdsman puts on the air for a cluster command from the coordinator. */
export function commandBytes(command, payload) {
  return Zcl.Frame.create(
    Zcl.FrameType.SPECIFIC, Zcl.Direction.CLIENT_TO_SERVER, false, MANUFACTURER_CODE, 9, command, I.cluster.id, payload, customClusters,
  ).toBuffer();
}

export {Zcl};
