Zigbee2MQTT loads every `.js`, `.cjs` and `.mjs` file of this folder (not subfolders) as an external converter.

- `mc-plant.mjs`: the PlantModule (hand-written).
- `mc-plant/codec.mjs`: encoding and decoding of the custom cluster (hand-written).
- `mc-plant/interface.mjs`: attribute and command tables, **generated** from `PlantModule/interface.yaml` by `Gateway/scripts/gen_converter.py`. Do not edit.

Test: `Gateway/scripts/test_converter.sh`. The compose file mounts this folder read-only: a converter that fails to load makes Zigbee2MQTT stop at start-up instead of renaming files in the repository.
