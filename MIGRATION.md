# Switching from travisghansen/hass-pfsense to this fork

This guide is for users who have the original integration
([travisghansen/hass-pfsense](https://github.com/travisghansen/hass-pfsense))
installed through the Home Assistant **Marketplace** (HACS, built into Home
Assistant since 2026.11) and want to switch to this fork **without losing
their pfSense setup, devices, entities or history**.

New installations don't need this guide: just add the fork as a custom
repository (see the [README](README.md#installation)).

## Why the normal way doesn't work

Both repositories install the same integration (domain `pfsense`) into the
same folder, `custom_components/pfsense`.

- **Installing the fork** fails with *"The pfsense directory belongs to
  travisghansen/hass-pfsense"*, because the Marketplace allows only one
  repository per integration folder.
- **Uninstalling the original** first is blocked with *"… is in use"* as long
  as the pfSense integration is set up.

> [!WARNING]
> Do **not** choose **Delete and uninstall** in that dialog. It deletes your
> pfSense setup together with all its devices and entities, and this can't be
> undone.

The workaround is to move the "installed" state from the original repository
to the fork in the Marketplace's storage file, and to replace the integration
files at the same time. Your pfSense setup is not touched, because the
integration domain and all unique IDs stay the same.

## Requirements

- Home Assistant 2026.11 or newer (with the Marketplace).
- The **Terminal & SSH** (or Advanced SSH & Web Terminal) app, to run
  commands. `jq`, `curl` and `unzip` are available there.
- A current backup (Settings → System → Backups).

## Steps

### 1. Add the fork as a custom repository

In Settings → Marketplace, add `https://github.com/betterbitsbites/hass-pfsense`
as a custom repository (type: Integration). Don't install it. Adding it creates
the storage entry that step 4 edits.

### 2. Stop Home Assistant

Home Assistant must be stopped, otherwise it overwrites the storage file when
it saves. The SSH terminal keeps running.

```bash
ha core stop
```

### 3. Back up the storage file and the integration folder

```bash
cp /config/.storage/marketplace.repositories /config/marketplace.repositories.bak
cp -a /config/custom_components/pfsense /config/pfsense.bak
```

Keep the backups **outside** `custom_components`. Every folder in there is
loaded as an integration, and a second copy of pfSense would clash.

### 4. Move the "installed" state to the fork

Set `VERSION` to the release you are installing (see
[Releases](https://github.com/betterbitsbites/hass-pfsense/releases)):

```bash
VERSION=v0.6.8

jq --arg v "$VERSION" '.data |= with_entries(
    if .value.full_name == "travisghansen/hass-pfsense" then
      .value |= (.installed = false | del(.version_installed, .installed_commit))
    elif .value.full_name == "betterbitsbites/hass-pfsense" then
      .value |= (.installed = true | .version_installed = $v)
    else . end)' \
  /config/.storage/marketplace.repositories > /tmp/marketplace.repositories
```

Check the result before applying it:

```bash
jq -c '.data[] | select(.full_name | test("/hass-pfsense$")) | {full_name, installed, version_installed}' \
  /tmp/marketplace.repositories
```

Expected output (two lines):

```
{"full_name":"travisghansen/hass-pfsense","installed":false,"version_installed":null}
{"full_name":"betterbitsbites/hass-pfsense","installed":true,"version_installed":"v0.6.8"}
```

If the `betterbitsbites` line is missing, step 1 didn't complete: run
`ha core start`, add the custom repository and start again from step 2.

If the output is as expected, apply it:

```bash
cp /tmp/marketplace.repositories /config/.storage/marketplace.repositories
```

### 5. Install the fork's files

```bash
curl -L -o /tmp/pfsense.zip \
  "https://github.com/betterbitsbites/hass-pfsense/releases/download/$VERSION/pfsense.zip"
rm -rf /config/custom_components/pfsense
mkdir /config/custom_components/pfsense
unzip /tmp/pfsense.zip -d /config/custom_components/pfsense
grep '"version"' /config/custom_components/pfsense/manifest.json
```

The last command should print the version you set in `VERSION` (without the
`v`).

### 6. Start Home Assistant

```bash
ha core start
```

### 7. Check

- Settings → Devices & services → pfSense shows the new version, with all
  devices and entities as before.
- The Marketplace lists `betterbitsbites/hass-pfsense` as installed and the
  original as not installed. Future releases of the fork show up as normal
  updates.

Once everything works you can delete `/config/pfsense.bak` and
`/config/marketplace.repositories.bak`.

## Rolling back

```bash
ha core stop
cp /config/marketplace.repositories.bak /config/.storage/marketplace.repositories
rm -rf /config/custom_components/pfsense
cp -a /config/pfsense.bak /config/custom_components/pfsense
ha core start
```

## Notes

- `marketplace.repositories` is an internal file of Home Assistant. Its format
  may change in future versions. If the commands in step 4 don't produce the
  expected output, don't apply the result; please
  [open an issue](https://github.com/betterbitsbites/hass-pfsense/issues)
  instead.
- If the Marketplace resets the change after the restart, the integration
  still runs on the new files. Updates then have to be installed manually by
  repeating step 5 with the new version.
