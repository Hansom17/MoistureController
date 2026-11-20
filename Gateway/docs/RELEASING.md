# Releasing the gateway app

A release is a git tag. **A tag installs itself on every gateway that follows its channel**, so a release is deliberate: it needs an approval click and the checks below.

## What a release contains

| File | Content |
|---|---|
| `moisture-app-X.Y.Z.tar.gz` | `api/` and `hub/` (complete source layout with `pyproject.toml`, without tests), `web/` (Flutter web build), `z2m/` (Zigbee2MQTT converters), `VERSION`. At the archive root, no top-level folder. Deterministic: the same inputs give the same bytes. |
| `manifest.json` | `{schema, version, channel, app_generation, asset, sha256, size, released_at}` |
| `manifest.json.sig` | raw ed25519 signature over the exact bytes of `manifest.json` |

`channel` is `stable` for `X.Y.Z` and `prerelease` for `X.Y.Z-alpha|beta|rc[.N]`. It is signed, so a gateway on the stable channel can refuse a pre-release even if the GitHub flag were changed.

A gateway verifies with `openssl pkeyutl -verify -pubin -inkey /etc/moisture/update-pubkey.pem -rawin -in manifest.json -sigfile manifest.json.sig`, then checks `sha256` of the tarball against the manifest. `Gateway/scripts/verify_release.sh <dir>` does the same.

## Channels (the updater on the device)

- **stable**: GitHub `releases/latest` (it never returns pre-releases or drafts).
- **newest**: the highest semver of all non-draft releases, pre-releases included (`1.0.0` is higher than `1.0.0-rc.1`).
- Requirements for the updater: install only if the version is higher than the installed one (never downgrade, also not when the channel is switched), only if `app_generation` equals the image's, only if `channel` is allowed for its channel.

## How to release

1. Everything for the release is merged to `main` and CI is green.
2. Check `Gateway/update/app_generation` (rule below). If dependencies changed, the image must be built and flashed first.
3. Create the tag on `main`: `git tag v1.2.3 && git push origin v1.2.3` (pre-release: `v1.3.0-rc.1`). Tag creation is limited to admins by the tag ruleset.
4. The workflow `Release` runs the checks (valid tag, commit on `main`, version higher than every existing release), the whole CI, and then waits for approval: **Actions, the run, Review deployments, tick `release`, Approve and deploy**.
5. The job builds the bundle, writes and signs the manifest, **verifies the signature with the public key before anything is uploaded**, creates a *draft* release, downloads the draft again and verifies it, and only then publishes it.
6. Stable releases are marked latest, pre-releases are marked pre-release and not latest.

If a release is bad, do not delete the tag: publish a higher version. Devices that installed it roll back by themselves only if the health check fails.

## app_generation

`Gateway/update/app_generation` holds one integer. A gateway only installs releases whose `app_generation` equals the one of its image. **Bump it whenever something differs that an update cannot bring to the device**:

- Python dependencies or `requires-python` of `api` or `hub` (the CI gate `deps-gate` fails with "bump app_generation and reflash required"),
- the Zigbee2MQTT version or the converters (`z2m/` ships in the bundle for the image build; the updater does not apply it),
- the MQTT contract, Mosquitto users or ACL, systemd units, anything that needs an OS-level change.

A bump means: a new `Gateway/update/deps-<n>.txt` (`python Gateway/scripts/check_deps.py --write`), a new image built from this release and flashed. Only then tag the first release of the new generation. Old devices keep running their last release of the old generation.

### Keeping `deps-<n>.txt` in sync with the image repo

This repo is the source of truth for what the app needs: `deps-<n>.txt` lists the requirements (normalised, api and hub merged). The image repo (moisture-gateway) must provide at least that. Recommended check in the image repo: fetch `deps-<n>.txt` from the release tag that the image is built from and fail if a listed package or version range is not satisfied by the image. The reverse (changing the image without this repo) does not need a bump here.

## Migrations: compatible for one version

The services migrate the database when they start. If the health check of a new release fails, the device restores the previous code and a database backup, so:

- a migration may add tables, columns (nullable or with default) and indexes
- dropping or renaming columns/tables, changing types, adding NOT NULL without default is done in **two releases**: first the code stops using the thing, a later release removes it
- CI (`check_migrations.py`) fails for new migrations that use `drop_column`, `drop_table`, `alter_column`, `rename_table`, `drop_constraint` or raw `execute`, unless the file contains `# migration-unsafe-ok: <reason>`. Use that only for a major release. It also fails when an already released migration is edited and when there is more than one head.
- The updater should take its database backup with SQLite `VACUUM INTO` (the hub does this in `services/backup.py`) and restore it together with removing `-wal`/`-shm` files. Data written after the update is lost on a rollback, so keep the health check window short.
- Restart order: hub, then api. The MQTT `CONTRACT` of two consecutive releases must stay compatible.

## Health check

The updater polls the unauthenticated `GET /api/v1/meta` of the api: HTTP 200 and `version` equal to the installed release. The hub has no HTTP port: `hub.online` in the same response (and `systemctl is-active mc-hub`).

## Signing key (ed25519)

The private key is the secret `UPDATE_SIGNING_KEY` of the GitHub **environment `release`** (PEM, PKCS#8). The public key is committed in `Gateway/update/update-pubkey.pem` and installed in the image as `/etc/moisture/update-pubkey.pem`.

- Generate: `openssl genpkey -algorithm ed25519 -out key.pem`, public part: `openssl pkey -in key.pem -pubout -out update-pubkey.pem`.
- Store: Settings, Environments, `release`, Environment secrets, add `UPDATE_SIGNING_KEY` with the content of `key.pem`. The environment has a required reviewer and may only run for tags `v*`. Do not keep a repository-level secret of the same name.
- **Back up** `key.pem` offline (password manager and a second offline copy). GitHub never shows a secret again. Never commit it, never print it in a workflow. Losing it means no further updates can be signed: every gateway needs a new image with a new public key.
- **Rotate**: a device trusts the public key(s) in its image. Without overlap, a new key means reflashing every device. For a rotation without reflash the device must accept more than one key (`/etc/moisture/update-pubkey.pem` with two keys, or several files): ship an image that trusts old and new, sign releases with the old key until all devices run that image, then switch the secret to the new key. Plan this before the first rotation is needed. If the key leaked, the old key stays trusted by all devices until they are reflashed, so keep the environment protections (reviewer, tag ruleset) strict.

## GitHub settings this process relies on

- Environment `release`: required reviewer (you), "Prevent self-review" off when you are the only reviewer, deployment tags `v*`.
- Tag ruleset for `v*`: only admins create, update or delete; no force push.
- `main`: pull request and green checks required (`Hub and api tests and lint`, `App analysis and tests`, `Zigbee2MQTT converter tests`, `Dependencies match the gateway image, migrations are update-safe`, `Update bundle builds, is deterministic and runs from its folder`).
