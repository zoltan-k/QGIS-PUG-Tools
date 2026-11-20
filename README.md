# PUG Tools

QGIS plugin for creating and validating Romanian PUG/PUZ/PUD/PATJ/PMUD
urban-planning GeoPackage projects. Validation rules mirror the official
beta validator at `datelocale.mdlpa.ro` (OMDLPA 904, PUG rules v3.0.0+),
cross-checked directly against MDLPA's own open-sourced reference
implementation ([`cod_validare`](https://github.com/DateLocale-MDLPA/cod_validare))
where the published rule descriptions were ambiguous or out of date.

See [CHANGELOG.md](CHANGELOG.md) for the release history.

## What it does

Ten tools, all available from the plugin toolbar/menu inside QGIS:

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
6. **Copie de siguranta portabila** — creates `<package folder name>.zip`
   (e.g. `HR_BALAN_83464_PUG_AAAALLZZ.zip`) next to the `.qgz`, containing the
   project (rewritten with strictly relative paths), the whole `..._AAAALLZZ`
   package folder, and `Alte_surse/` with any file-based layers that lived
   outside the package (paths rewritten relative). It asks whether to save
   unsaved changes, and warns that memory layers are lost and that URI/virtual
   layers stay as they are. The open project is never modified.
   **Consolideaza straturile** (fourth button in the first group) — when the
   template layers of a project come from several `.gpkg` files, brings them
   into one: pick the target (only standard `<JUD>_<UAT>_<SIRUTA>_<TIP>_<date>.gpkg`
   names qualify, `AAAALLZZ` preselected; if none qualifies a new gpkg is built
   from the template), tables from the other files replace the target's
   (`_*` reference tables are only re-pointed). Saves everything and makes a
   backup zip first; source files are never deleted, and files the project no
   longer references are ignored by backups and the portable copy.
7. **Editeaza sablonul** / **Salveaza sablonul** — safely edit the bundled
   template's structure, styles, and field properties, with protection
   against leftover features in layers that must ship empty.
8. **Despre** — plugin info and local-data status (template, UAT boundary
   cache), with delete/refresh actions, validation settings, and
   **Verifica actualizari** (manual only; see below).

### Despre: validation settings

- **Geometry warning tolerance (R26/R27).** Geometries strictly inside the
  boundary (buffer 0 m, fixed — the value published by the official validator)
  pass silently. Beyond that but within the tolerance: WARNING on rules 26 and
  27, not a failure. Beyond the tolerance: failure (BLOCKER). Default 10 m, per
  the OMDLPA 904 technical specifications.
- **Local copy of the GPKG during validation.** A GPKG is a SQLite database: on
  a network share every small read and file lock is a round-trip, and the rules
  reopen the file dozens of times, so validation can take many times longer than
  locally. With a local copy the GPKG is copied once to a temporary folder
  (deleted afterwards) and the rules read from the copy; the original is never
  modified. *Auto*: only when the project is on a network drive (UNC path or
  mapped drive, e.g. `T:\`). *Always*: also for local drives or unrecognised
  network drives (e.g. some cloud drivers). *Never*: read the original file
  directly. Applies from the next validation.

### Despre: updates

**Verifica actualizari** looks up the latest public release on GitHub
(`zoltan-k/QGIS-PUG-Tools`) and shows its notes. **Descarca si instaleaza**
downloads the release zip, verifies its SHA-256 and contents, saves the current
version to a temporary folder, and installs through QGIS's own "Install from
ZIP" mechanism. Nothing runs automatically; there is no startup check. Install
is disabled for development copies (symlinked or git checkouts).

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
