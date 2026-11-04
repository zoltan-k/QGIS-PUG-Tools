# PUG Tools

QGIS plugin for creating and validating Romanian PUG/PUZ/PUD/PATJ/PMUD
urban-planning GeoPackage projects. Validation rules mirror the official
beta validator at `datelocale.mdlpa.ro` (OMDLPA 904, PUG rules v3.0.0+),
cross-checked directly against MDLPA's own open-sourced reference
implementation ([`cod_validare`](https://github.com/DateLocale-MDLPA/cod_validare))
where the published rule descriptions were ambiguous or out of date.

See [CHANGELOG.md](CHANGELOG.md) for the release history.

## What it does

Eight tools, all available from the plugin toolbar/menu inside QGIS:

1. **Validare** — runs the full set of validation rules against a
   GeoPackage's layers (attribute correlation, allowed values, value
   structure, geometry, sliver polygons, temporal consistency, structural
   conformance to the template, and more).
2. **Ruleaza validari selective** — runs only the rules the user checks.
3. **Proiect nou PUG** — creates a new PUG/PUZ/PUD/PATJ/PMUD project for any
   UAT in Romania, with the administrative boundary fetched dynamically
   (no need to bundle the full national dataset).
4. **Pregateste pentru validare** — archives the current project with a
   timestamp, ready for official submission.
5. **Actualizeaza pachetul** — brings an existing project up to the current
   template's structure and styles (missing reference layers, styles),
   without touching content-layer data.
6. **Editeaza sablonul** / **Salveaza sablonul** — safely edit the bundled
   template's structure, styles, and field properties, with protection
   against leftover features in layers that must ship empty.
7. **Despre** — plugin info and local-data status (template, UAT boundary
   cache), with delete/refresh actions.

## Requirements

QGIS >= 3.28, Qt5 or Qt6 build.

## Installation

1. Download the repository as a ZIP from
   [https://github.com/zoltan-k/QGIS-PUG-Tools](https://github.com/zoltan-k/QGIS-PUG-Tools) (Code → Download ZIP), or clone it.
2. Make sure the plugin folder is named `PUGTools` (QGIS uses the folder name
   as the plugin id), e.g. rename the extracted `QGIS-PUG-Tools-main` folder.
3. Copy it into your QGIS profile's `python/plugins` folder (QGIS: Settings →
   User Profiles → Open Active Profile Folder), or zip the `PUGTools` folder and
   use Plugins → Manage and Install Plugins → Install from ZIP.
4. Enable **PUG Tools** in the plugin manager.

## Project

Source and issue tracker: [https://github.com/zoltan-k/QGIS-PUG-Tools](https://github.com/zoltan-k/QGIS-PUG-Tools). The plugin is not currently published
to the official QGIS Plugin Repository. `SBOM.cdx.json` lists dependencies and
bundled assets; `dev/` holds maintainer tooling and is not part of the plugin.

## License

Copyright (C) 2026 Zoltán Kelemen. PUG Tools is free software, licensed under
the **GNU General Public License, version 3 or (at your option) any later
version** (`GPL-3.0-or-later`); see [LICENSE](LICENSE). The licence covers the
plugin code. The bundled template, reference data and documents (SIRUTA table,
schema, template structure) originate from the official MDLPA specification and
remain subject to their own terms.
