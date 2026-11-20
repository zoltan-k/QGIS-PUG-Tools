# Changelog

PUG Tools — QGIS plugin for creating and validating Romanian
PUG/PUZ/PUD/PATJ/PMUD urban-planning GeoPackage projects. Validation rules
follow the official validator at `datelocale.mdlpa.ro` (OMDLPA 904, PUG
rules v3.0.0+).

Only the milestones that are still relevant are listed. Earlier development
versions (1.x) are summarized at the bottom.

## 2.2.6.0
- Template updated to the official 3.1.1 (validation package 2026.11.13): lookup tables are now `sys_*` (was `_*`), version table `sys_versiune`; "Despre" shows "Sablon PUG - versiunea curenta: V3.1.1".
- "Actualizeaza pachetul" migrates older projects (3.0.x / 3.1.0) to the new names, keeps the project type and all content data, warns when an old lookup table held values missing from the official list, and offers to refresh an outdated active template copy (also offered by "Proiect nou PUG"). `_*` tables of older projects are still recognised.
- Rule 10: `POT_detaliu`, `CUT_detaliu`, `Clad_Hmax_detaliu` of `RegulamentLocalUrbanismDetaliat` are optional; the plugin's `layer_styles` table is no longer counted as a missing template layer.
- Rule 12: in `RegulamentLocalUrbanismDetaliat` a record fails only if all of POT/CUT/Clad_Hmax and their `_detaliu` columns are empty (0 / "Nu este cazul" count as filled).
- Rule 17: uniqueness of `Cod_ZF_ZRS` (RLU), `Cod_SZF_ZRS_D` and `Tip_SZF_ZRS_D` (RLUD); each RLU code must exist in `sys_zona` with matching `Tip_ZF_ZRS` and `Tip_zona`.

## 2.2.5.2
- Fix: "Actualizeaza pachetul" no longer drops every layer of the REF group when it moves the group to the end of the tree.
- "Consolideaza straturile" now also merges data layers whose source table is named differently (for example a "Save Features As" export); layers it cannot move are listed in the dialog, and merged layers get the main GPKG default style.
- "Actualizeaza pachetul" re-applies the GPKG default style on package layers whose field widgets/defaults differ from it.

## 2.2.5.1
- New in "Despre": **Verifica actualizari** (manual only) shows the latest public release and its notes;
  **Descarca si instaleaza** downloads the release zip, verifies its SHA-256 and contents, keeps a backup of the
  current version in the temp folder and installs it through QGIS's own "Install from ZIP". Disabled for
  development copies (symlinks / git checkouts).
- The long explanations of the validation settings moved from the dialog to the README.

## 2.2.5.0

- **Much faster validation when the project is on a network share or mapped drive.** A GeoPackage is a SQLite database, and over a network every small read and file lock is a round trip, so validating a real project from a mapped drive took almost 6 minutes (about 2.5 seconds with this version). Validation now copies the `.gpkg` once to a local temporary folder, runs all rules against the copy and deletes it afterwards; the original file is only read, never written. If the copy fails, the rules read the original as before.
- New setting in **Despre** (section "Validare - acces la fisiere (retea)"): **Automat** (default; only for network locations - UNC paths and mapped drives such as `T:\`), **Intotdeauna** (also for local drives or network drives that Windows reports as local, e.g. some cloud-drive drivers) or **Niciodata** (read the original file directly).
- Per-rule and total validation times are written to the QGIS log panel, tab "PUG Tools".

## 2.2.4.1

- New **Repara R19** buttons (one for RegulamentLocalUrbanism, one for RegulamentLocalUrbanismDetaliat) in the validation results. They add one provisional row per code that R19 reports as missing from the regulament layer: code and type come from ZFPropusa / ZonaReglementareSuplimentara, `Tip_zona` is set from the matching domain, other text fields get `-` and numeric fields `0`.
- Nothing existing is deleted or changed; NULL source values and type mismatches for an existing code are skipped. A warning (in the confirmation and in the result) reminds that the user must complete the RLU/RLUD details afterwards.
- New fourth toolbar tool **Consolideaza straturile intr-un singur GPKG** (introduced in 2.2.4.0, not published separately): when the template layers of a project come from several `.gpkg` files, it brings them into one target GeoPackage after saving the project and making a backup zip; source files are never deleted.

## 2.2.3.7

- New **Repara R22** button in the validation results. It deletes every feature of `RegulamentLocalUrbanism` and `RegulamentLocalUrbanismDetaliat` that fails rule 22 (cod/tip pair not found in ZFPropusa / ZonaReglementareSuplimentara, or NULL) - all of them, not only the first 100 listed.
- A warning dialog comes first: choose Yes to proceed, or No to cancel and fix the features manually.
- On Yes, a timestamped GeoPackage-only backup (`<name>_backup_YYYYMMDD_HHMMSS.gpkg`) is written next to the project file before anything is deleted; without a backup nothing is modified.

## 2.2.3.6

- New **Repara R25** button in the validation results (invalid or missing geometries). For every layer R25 reports: features with no geometry are deleted; features with invalid geometry get the geometry (geometry only, same feature id) from a temporary *Fix geometries* output, which is then discarded.
- Before any change, a timestamped GeoPackage-only backup (`<name>_backup_YYYYMMDD_HHMMSS.gpkg`) is written next to the project file; without a backup nothing is modified.
- A repaired geometry that no longer fits the layer's geometry type is left unchanged and listed in the result.
- The partial validator's rule picker starts with no rule checked and remembers the rules from the last run.

## 2.2.3.4

- The portable copy and the backup made before **Actualizeaza pachetul** now
  checkpoint the GeoPackage first (`PRAGMA wal_checkpoint(TRUNCATE)`), so recent
  edits are inside the `.gpkg` and the `-wal` file in the zip is empty. Works
  with QGIS open; if the file is locked the backup still proceeds and includes
  the `-wal`/`-shm` files as before.

## 2.2.3.3

- **Portable copy**: no longer fails when a layer's file is on a different drive
  than the project (e.g. a DXF on `T:` with the project on `D:`); the file is
  copied into `Alte_surse` like any other external source.
- `package_updater` (**Actualizeaza pachetul**), copying missing template files:
  - folders `1_`, `2_`, `3_`: a template PDF is copied only if the folder has no
    file with the same numeric prefix (e.g. `1_3_`). A file with the same prefix
    but a different name is left as is and listed as a warning in the result.
  - folder `4_Avize_acorduri`: nothing is added if it already contains any PDF
    starting with `4_`; if it has none, all template PDFs are added.

## 2.2.3.2

- `package_updater` (**Actualizeaza pachetul**): the backup made before an update
  now contains the project and the **whole package folder** (all subfolders),
  like the portable copy. The folder and the GeoPackage can have any name, e.g.
  already renamed with a date instead of `AAAALLZZ`.
- Layers from other sources (external files, WMS, virtual, ...) are never removed
  from the project just because their name matches a dropped reference table;
  they stay as they are.
- The portable copy no longer prefers a `*_AAAALLZZ` folder: the folder of the
  `PlanSpatial` layer is used whatever it is called.

## 2.2.3.0

- `package_updater` (**Actualizeaza pachetul**): a damaged `layer_styles` table
  no longer leaves the GeoPackage permanently "malformed". The renamed
  corrupted copy is now removed from the file (`DROP TABLE`, or a schema edit
  plus `VACUUM` when the pages are unreadable), so running the update a second
  time no longer stops with "database disk image is malformed". Packages left
  in that state by earlier versions are cleaned on the next run.
- RLUD `Clad_Hmax`/`POT` are retyped to `Integer64` in the first run, so rule 10
  passes right after the update (previously only after a second run).
- The confirmation dialog lists only real differences and reports "already up
  to date" (without making a backup) when there is nothing to do.

## 2.2.2.1

- Fixed the `Judet` default of the `LimitaIntravilanExistenta` and
  `LimitaIntravilanPropusa` layers: it was computed from the new feature's own
  (empty) `SIRUTA` and stayed blank. It is now
  `aggregate('~REF_UAT','max',"county")`, taken from the project's reference UAT.
  Template-only change; refresh the active template copy from the About dialog.

## 2.2.2.0

- New **Copie de siguranta portabila** toolbar button: one zip next to the
  `.qgz` holding the project (strictly relative paths), the whole package
  folder and `Alte_surse/` for file-based layers from outside the package.
  Prompts to save unsaved changes (a failed save stops the process) and
  warns about memory layers (lost) and URI/virtual layers (kept as is).

## 2.2.1.0

- `package_updater`: layers of dropped tables are now removed by source
  (including renamed layers), and a final sweep removes layers whose table no
  longer exists, so reopened projects have no missing layers.
- SBOM restructured (CycloneDX 1.5 + VEX); `dev/cpr_precheck.py` added for
  pre-release dependency/vulnerability checks.

## 2.2.0.0

- Bundled template updated to published schema **3.1.0** (`sys__versiune`
  reference layer, RLUD `Integer64`, lookup tables synced).
- `package_updater` migrates `__versiune`, lookup tables,
  `PlanSpatial.Stadiu` and RLUD column types.
- Rules R10/R12/R16/R24/R30 aligned with the published rules.
- "Actualizeaza pachetul" button added to the validation results dialog.
- `SBOM.cdx.json` added.

## 2.1.0.0

- Double-clicking a validation result activates the layer, selects and zooms
  to the feature and opens the attribute table filtered to it (no-op for
  layer-level failures).

## 2.0.x

- PUZ and other non-PUG project types supported (`__versiune.tip` fixes;
  PlanSpatial UAT-refetch action made robust; UAT name prefix removed; RLUD
  text fields multiline).
- `package_updater` backup no longer fails when the project and the GPKG are on
  different drives (2.0.1.1).

## 1.9.x

- **1.9.2.0** — Bundled template updated to published schema 3.0.3 (`_siruta`
  restructure, RLUD numeric columns); active-template staleness warning.
- **1.9.1.x** — Toolbar reorganized; template editing moved into the About
  dialog; icons moved to `ui/icons/`.
- **1.9.0.x** — "Repara" one-button fixes for R18/20/21/26/27/31/32/33/34;
  stale reference-table cache fixes in R13/R16/R20; `package_updater`
  self-heals the `~vREF_SZF_ZRS_D` virtual reference layer.

## 1.8.x

- **1.8.8.0** — `package_updater` cleans up legacy reference tables,
  repositions the REF group, repairs `layer_styles` corruption and syncs
  missing template files.
- **1.8.7.x** — Rules 35 and 36; R26/R27 boundary buffer + warning, R15
  expiry fix; RLUD schema migration; reference layers no longer get styles
  saved.
- **1.8.6.x** — Rule 10 (GPKG structure conformance to the template);
  `ZFPropusa.Arie_ZF` default fixed.
- **1.8.5.x** — `~REF_UAT` is a persistent GPKG layer; R26 uses it;
  `package_updater` self-heals `layer_styles` and re-adds missing reference
  layers.
- **1.8.0.0** — Package updater tool with mandatory pre-update backup.

## Earlier (1.x) — summary

- **1.7.0.0** — About panel (template/cache status, delete/refresh actions).
- **1.6.0.0** — Administrative boundary of the chosen UAT fetched dynamically
  (any county) instead of being bundled.
- **1.5.x** — Rule ID and severity shown in the results table; selective
  validation button.
- **1.4.0.0** — Validation rules 12–34 implemented.
- **1.3.5.4** — Starting point (rules 11, 19, 30).

## Notes for contributors

- Changes are verified against real QGIS (headless, Qt5 and Qt6 builds) and
  not only by syntax checks.
- Run `python dev/cpr_precheck.py` before a release to check the SBOM against
  installed versions and known vulnerabilities.
