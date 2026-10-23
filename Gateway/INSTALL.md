# Setting up the gateway on its own device

This takes a blank small computer to a running gateway: Zigbee coordinator, Zigbee2MQTT, Mosquitto, the `hub`, the `api` and the web app. Everything runs in Docker. Design background: [`specs.md`](specs.md); the short version of this page is [`readme.md`](readme.md).

The one command that does steps 5 and 6 is `Gateway/scripts/install.sh` (`--check` only looks and changes nothing).

## 1. What you need

| Part | Notes |
|---|---|
| **A small computer** | Raspberry Pi 4/5 (2 GB is enough) or any mini PC or old laptop. 64-bit (arm64 or amd64), wired network preferred, 8 GB free disk. |
| **Zigbee coordinator** | The SONOFF Dongle Plus MG24 (EmberZNet, adapter `ember`) used during development. Plug it into a USB port, ideally on a short extension cable away from the computer and from USB 3 devices (interference). |
| **A computer with Flutter** | Only to build the web app once (step 4). Or copy a prebuilt `App/build/web` from someone who has built it. |
| **Your network** | The gateway only needs your home network. It needs **no cloud and no account**. Do not expose its port to the internet. |

## 2. Prepare the device

1. Install a 64-bit Linux (Raspberry Pi OS Lite 64-bit or Debian 12), enable SSH, and give the device a fixed address (a DHCP reservation in your router is easiest). Set the hostname, for example `moisture`.
2. Set the time zone and make sure the clock is synchronised (rules, quiet hours and daily limits use it):
   ```bash
   sudo timedatectl set-timezone Europe/Berlin
   timedatectl      # "System clock synchronized: yes"
   ```
3. Install Docker Engine and the compose plugin, then allow your user to use it:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER      # log out and in again
   docker compose version
   ```
4. Install `git` and `openssl` if they are missing: `sudo apt install -y git openssl curl`.

## 3. Get the code onto the device

```bash
git clone <your repository> moisture && cd moisture
```
Without a remote, copy the folder from your computer instead (`rsync -a --exclude .git --exclude App/build ./ moisture@<device>:moisture/`). The gateway needs `Gateway/` only; `App/build/web` comes in the next step.

## 4. Build and copy the web app (on your computer)

```bash
cd App
flutter build web --release --no-web-resources-cdn
rsync -a build/web/ moisture@<device>:moisture/App/build/web/
```
The web build is plain files that the `api` serves; nothing is baked into it, it talks to the server it was loaded from. Repeat this step whenever the app changes.

## 5. Plug in the dongle and install

```bash
Gateway/scripts/install.sh --check     # looks, changes nothing
Gateway/scripts/install.sh             # does it
```
What the script does, so you can also do it by hand:

1. Checks Docker, the compose plugin, openssl, the clock, the web build, the port and the dongle.
2. `scripts/setup.sh`: creates `Gateway/firmware/.env` with **generated MQTT passwords** for `hub`, `api` and `z2m` and the Mosquitto password file. Run it again later and the passwords stay.
3. Writes `ZIGBEE_DEVICE` (the dongle's stable path from `/dev/serial/by-id/`) and `WEB_DIR` into `.env`. If several serial devices are connected it asks you to set `ZIGBEE_DEVICE` yourself.
4. `docker compose up -d --build` (the first start builds the `hub` and `api` images, a few minutes on a Pi).
5. Waits for the `api` and prints the address and the **setup code**.

Settings you may want in `Gateway/firmware/.env`: `MC_PORT` (default 80), `ZIGBEE_ADAPTER` (default `ember`), `MC_INSTANCE_ID`.

## 6. First visit

Open `http://<device address>/` in a browser, enter the **setup code** from the install output (or `docker compose logs api | grep 'SETUP CODE'`), choose the installation name and time zone and create the **owner account**. Then, in the app:

- **Settings → Installation settings:** check the time zone, the battery thresholds and, if you want alerts on your phone, the Telegram token and chat id.
- **Settings → Users:** invite the people who should have access (admin, member, viewer).

## 7. Add your modules

1. In the app: **Devices → Add device**. The join window opens (about two minutes).
2. Power the module. A module that has never joined looks for a network by itself for three minutes (fast LED blink). One that belonged to another network (for example your bench setup) must be reset first: **hold the button for 10 seconds**, it restarts and then looks for a network.
3. The module appears live: joined, interview, configure, ready. Name it and open **Edit configuration** to set its slots (moisture sensor, pump) and ports. Then create a **plant** from a moisture slot and a pump slot.
4. Try **Water now** for a few seconds.

Development builds of the module join with the default Zigbee link key (`MC_DEV_JOIN`). Install codes for production modules need the provisioning tool, which is not written yet.

**Moving an existing Zigbee network from the bench:** the simplest way is to re-pair the modules as above. To keep the network, copy `network_key`, `pan_id`, `ext_pan_id` and `channel` from the old `configuration.yaml` into the `advanced:` section of the new one (`docker compose exec zigbee2mqtt vi /app/data/configuration.yaml`, then `docker compose restart zigbee2mqtt`) before any module joins.

## 8. Check that it works

```bash
cd Gateway/firmware
docker compose ps                         # four running: mosquitto, zigbee2mqtt, hub, api (z2m-init has finished and exited)
docker compose logs --tail 30 zigbee2mqtt # "Zigbee2MQTT started!", "Currently N devices are joined"
docker compose logs --tail 30 hub api
```
In the app, **Settings → Gateway** shows Zigbee2MQTT, the coordinator, the hub, the clock and the database size. It starts on every boot (`restart: unless-stopped`); reboot the device once and check that the app comes back.

## 9. Everyday operation

| Task | Command (in `Gateway/firmware`) |
|---|---|
| **Update** | `git pull`, rebuild the web app (step 4) if the app changed, then `docker compose up -d --build`. The databases migrate themselves. |
| **Backup** | `../scripts/backup.sh` copies the databases and the whole Zigbee2MQTT data (**the network key: without it every module has to join again**). Run it before updates and keep the folder off the device. The hub also makes a nightly copy of its database. |
| **Restore Zigbee data** | `docker compose down`, then `docker run --rm -v moisture_z2m-data:/data -v "$PWD/<backup>/z2m-data:/in" alpine cp -r /in/. /data/`, then `docker compose up -d`. |
| **Logs** | `docker compose logs -f hub` (or `api`, `zigbee2mqtt`, `mosquitto`) |
| **Restart one service** | `docker compose restart hub` |
| **Stop everything** | `docker compose down` (keeps all data; `down -v` **deletes it**) |
| **Change the dongle** | Set `ZIGBEE_DEVICE` in `.env`, then `docker compose up -d zigbee2mqtt`. A new coordinator makes a new network unless you restore the old coordinator backup. |

## 10. The api on another device (optional)

The `api` can run on a different machine, for example one that is reachable from outside while the Zigbee box stays hidden. It talks to the box's Mosquitto over TLS:

```bash
Gateway/scripts/remote-api.sh <address of this box>        # on the gateway box: CA, certificate, TLS listener 8883
docker compose -f docker-compose.yml -f docker-compose.remote.yml up -d
```
and on the other device `docker compose -f docker-compose.api.yml up -d` with the copied `ca.pem` and a small `.env` (the script prints the exact steps). Reaching it from outside your home needs a VPN or an HTTPS reverse proxy; that is not part of this setup.

## 11. When something does not work

| Symptom | Look at |
|---|---|
| `install.sh` says no serial device | The dongle is not seen: `lsusb`, another cable or port, `ls /dev/serial/by-id/`. |
| Zigbee2MQTT restarts with `Failed to start EZSP` / `No such file` | `ZIGBEE_DEVICE` in `.env` is wrong or the dongle is in use by another program (another Zigbee2MQTT on the same dongle). |
| `docker compose up` says port is in use | Another web server on port 80: set `MC_PORT=8080` in `.env`. |
| The app says the gateway or the hub is unreachable | `docker compose ps`; `docker compose logs hub api mosquitto`. `hub` and `api` need the passwords in `.env` and `mosquitto/passwd` to match (run `scripts/setup.sh` again, then `docker compose up -d`). |
| A module does not join | Is the join window open (countdown in the app)? Is the module reset (10 s button hold)? Is it near the dongle? Zigbee channel 25 is used; a very noisy 2.4 GHz environment can need a different one (`advanced.channel`, rejoin required). |
| A module joined but shows no readings | The configure step after the join probably failed. Remove the device in the app and join it again (the join runs configure), and check `docker compose logs zigbee2mqtt` for converter errors. |
| Times are wrong, rules fire at odd hours | The clock or the installation time zone (step 2 and Settings → Installation). |
| Everything was fine and is gone after a reinstall | `docker compose down -v` deletes the volumes. Restore from the backup (step 9). |

## 12. Where things are

| What | Where |
|---|---|
| Passwords, dongle path, port | `Gateway/firmware/.env` (mode 600, never commit it) |
| Mosquitto users and rules | `Gateway/firmware/mosquitto/passwd` and `acl` (`hub`, `api` and `z2m` each see only their own topics) |
| Databases and Zigbee data | Docker volumes `moisture_hub-data`, `moisture_api-data`, `moisture_z2m-data`, `moisture_mosquitto-data` |
| Zigbee2MQTT converter for the module | `Gateway/firmware/zigbee2mqtt/external_converters/` (mounted read-only into the container) |
| What is published | Only the `api` port (`MC_PORT`). MQTT, Zigbee2MQTT and the hub stay on the container network. |
