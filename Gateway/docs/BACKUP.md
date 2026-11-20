# Backup and restore of a packaged (Yocto) gateway

A gateway that runs the packaged services (systemd units `moisture-hub`, `moisture-api`, `zigbee2mqtt`, `mosquitto`) is backed up from your computer, so the file survives when the image is installed again:

```bash
Gateway/scripts/gateway_backup.sh [--encrypt] [--out DIR] [root@moisture.local]
Gateway/scripts/gateway_restore.sh [--dry-run] [--yes] ARCHIVE [root@moisture.local]
```

The archive holds consistent copies of `hub.db` (devices, plants, rules, readings, settings) and `api.db` (users, logins) and the Zigbee2MQTT files (`configuration.yaml` with the network key and channel, `coordinator_backup.json`, `database.db` with the paired devices, `state.json`). With the same coordinator dongle plugged in, a restore brings the Zigbee network back as it was, and the modules keep working without joining again. It contains secrets (network key, password hashes, Telegram token): keep it private or use `--encrypt` (passphrase asked, or `MC_BACKUP_PASSPHRASE`).

Restore: install the image, make sure ssh as root works, plug in the dongle, then `gateway_restore.sh ARCHIVE`. `--dry-run` checks the archive and the databases on the gateway and changes nothing. A real restore keeps the current files in `/root/before-restore-<time>.tgz`, stops the three services, replaces the files and starts them again; it refuses a backup whose database schema is newer than the software on the gateway. Make a backup before every update of the image.
