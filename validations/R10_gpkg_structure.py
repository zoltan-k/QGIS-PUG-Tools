# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica structura fisierul GPKG sa fie conform
template-ului publicat.

Structura fisierului activ este comparata cu structura sablonului PUG
(vezi tools/template_paths.py), in aceeasi ordine descrisa de regula
publicata:
    1. Sistemul de coordonate (pentru fiecare strat spatial).
    2. Numarul de straturi (documentatia >= sablon; straturi suplimentare
       din documentatie sunt ignorate).
    3. Numele straturilor (fiecare strat din sablon trebuie sa existe in
       documentatie; comparatie case-insensitive; se raporteaza cele lipsa).
    4. Tipul de geometrie (pentru fiecare strat prezent in ambele, tipul
       trebuie sa fie identic cu cel din sablon).
    5. Numarul de campuri (documentatia >= sablon, per strat).
    6. Numele campurilor (fiecare camp din sablon trebuie sa existe in
       stratul corespunzator din documentatie; se raporteaza cele lipsa,
       grupate pe strat).
    7. Tipul de date al campurilor (pentru fiecare camp prezent in ambele,
       tipul trebuie sa fie identic; se raporteaza cele gresite, grupate
       pe strat).

Nu se verifica continutul inregistrarilor. Straturile/campurile care exista
in documentatie dar nu exista in sablon nu sunt verificate.

Straturile de referinta (nume care incep cu "_" sau "~") sunt excluse din
comparatie, din ambele fisiere, inainte de orice verificare - un tabel de
lookup lipsa sau cu schema diferita (ex. "_hilucs", "_tip_ru", "~REF_UAT")
nu trebuie sa faca aceasta regula sa esueze. Prefixul "_" se aliniaza cu
codul sursa al validatorului oficial (cod_validare, utils.py:read_gpkg_data
filtreaza explicit `if not gpkgLayerName.startswith("_")` inainte de a
construi structura de comparat); "~" e o extindere deliberata dincolo de
comportamentul oficial (validatorul NU il filtreaza), ceruta explicit
pentru acest plugin.

Sablonul folosit pentru comparatie este cel activ (vezi
tools/template_paths.py: suprascriere manuala > copie activa din profilul
QGIS > sablonul din fabrica), NU neaparat cel bundled cu plugin-ul - daca
utilizatorul si-a personalizat sablonul (structura), validarea reflecta
acea structura personalizata, nu una din fabrica posibil irelevanta.
"""

from osgeo import ogr

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, find_gpkg_path

try:
    from ..tools import template_paths
except ImportError:  # pragma: no cover - fallback pentru rulare in afara plugin-ului
    from tools import template_paths

IGNORED_PREFIXES = ("_", "~")


class GpkgStructureMatchesTemplateRule(BaseValidationRule):
    """Fara parametri de configurare; sablonul de referinta este rezolvat automat."""

    def __init__(self, name, description="", rule_id=10):
        super().__init__(name, description, rule_id)

    # -- introspectie structura GPKG (schema, fara continut) ------------------

    @staticmethod
    def _describe_gpkg(path):
        """
        Returneaza {nume_strat_lower: {"name": nume_original, "geom_type": str,
        "srs": str sau None, "fields": {nume_camp_lower: (nume_original, tip_str)}}}
        pentru toate straturile OGR dintr-un fisier GPKG. ds este pastrat in
        viata de apelant (returnat separat) cat timp structura e folosita.
        """
        ds = ogr.Open(path, 0)
        if ds is None:
            raise ValueError(f"Nu s-a putut deschide fisierul GPKG:\n{path}")

        layers = {}
        for i in range(ds.GetLayerCount()):
            lyr = ds.GetLayerByIndex(i)
            name = lyr.GetName()
            if name.startswith(IGNORED_PREFIXES):
                continue
            srs = lyr.GetSpatialRef()
            srs_desc = None
            if srs is not None:
                authority = srs.GetAuthorityCode(None)
                srs_desc = f"EPSG:{authority}" if authority else srs.ExportToWkt()

            defn = lyr.GetLayerDefn()
            fields = {}
            for j in range(defn.GetFieldCount()):
                fdefn = defn.GetFieldDefn(j)
                fields[fdefn.GetName().lower()] = (fdefn.GetName(), fdefn.GetTypeName())

            layers[name.lower()] = {
                "name": name,
                "geom_type": ogr.GeometryTypeToName(defn.GetGeomType()),
                "srs": srs_desc,
                "fields": fields,
            }
        return ds, layers

    # -- core logic -------------------------------------------------------------

    def run(self, project):
        try:
            template_dir = template_paths.resolve_template_dir(ensure_active_copy=True)
        except template_paths.TemplateNotFoundError as exc:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name="-",
                    fid=0,
                    reason=f"Sablonul de referinta nu a putut fi gasit: {exc}",
                )
            ]
        template_gpkg = template_dir + template_paths.GPKG_RELATIVE

        try:
            gpkg_path = find_gpkg_path(project)
        except ValueError as exc:
            return [
                ValidationFailure(
                    rule_name=self.name, layer_name="-", fid=0, reason=str(exc)
                )
            ]

        template_ds, template_layers = self._describe_gpkg(template_gpkg)
        doc_ds, doc_layers = self._describe_gpkg(gpkg_path)

        failures = []

        # 1. sistemul de coordonate, per strat spatial prezent in ambele fisiere
        for key, tmpl_info in template_layers.items():
            if tmpl_info["srs"] is None:
                continue  # strat fara geometrie (tabel de referinta simplu)
            doc_info = doc_layers.get(key)
            if doc_info is None:
                continue  # raportat separat mai jos (strat lipsa)
            if doc_info["srs"] != tmpl_info["srs"]:  # inclusiv strat fara SRS in documentatie
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=tmpl_info["name"],
                        fid=0,
                        reason=(
                            f"Sistem de coordonate diferit fata de sablon: "
                            f"{doc_info['srs']} (asteptat {tmpl_info['srs']})."
                        ),
                    )
                )

        # 2. numarul de straturi (documentatie >= sablon)
        if len(doc_layers) < len(template_layers):
            failures.append(
                ValidationFailure(
                    rule_name=self.name,
                    layer_name="-",
                    fid=0,
                    reason=(
                        f"Fisierul GPKG contine {len(doc_layers)} straturi, mai putine "
                        f"decat sablonul ({len(template_layers)})."
                    ),
                )
            )

        # 3. numele straturilor (fiecare strat din sablon trebuie sa existe)
        missing_layers = sorted(
            info["name"] for key, info in template_layers.items() if key not in doc_layers
        )
        if missing_layers:
            failures.append(
                ValidationFailure(
                    rule_name=self.name,
                    layer_name="-",
                    fid=0,
                    reason=(
                        f"Straturi lipsa fata de sablon ({len(missing_layers)}): "
                        f"{', '.join(missing_layers[:MAX_REPORTED])}"
                    ),
                )
            )

        # 4-7: verificari per strat prezent in ambele fisiere
        for key, tmpl_info in template_layers.items():
            doc_info = doc_layers.get(key)
            if doc_info is None:
                continue  # deja raportat la pasul 3

            # 4. tipul de geometrie
            if doc_info["geom_type"] != tmpl_info["geom_type"]:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=tmpl_info["name"],
                        fid=0,
                        reason=(
                            f"Tip de geometrie diferit fata de sablon: "
                            f"{doc_info['geom_type']} (asteptat {tmpl_info['geom_type']})."
                        ),
                    )
                )

            # 5. numarul de campuri (documentatie >= sablon)
            if len(doc_info["fields"]) < len(tmpl_info["fields"]):
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=tmpl_info["name"],
                        fid=0,
                        reason=(
                            f"Numar de campuri ({len(doc_info['fields'])}) mai mic decat "
                            f"sablonul ({len(tmpl_info['fields'])})."
                        ),
                    )
                )

            # 6. numele campurilor
            missing_fields = sorted(
                fname
                for fkey, (fname, _) in tmpl_info["fields"].items()
                if fkey not in doc_info["fields"]
            )
            if missing_fields:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=tmpl_info["name"],
                        fid=0,
                        reason=(
                            f"Campuri lipsa fata de sablon ({len(missing_fields)}): "
                            f"{', '.join(missing_fields[:MAX_REPORTED])}"
                        ),
                    )
                )

            # 7. tipul de date al campurilor prezente in ambele
            wrong_type_fields = []
            for fkey, (fname, ftype) in tmpl_info["fields"].items():
                doc_field = doc_info["fields"].get(fkey)
                if doc_field is None:
                    continue  # deja raportat la pasul 6
                doc_fname, doc_ftype = doc_field
                if doc_ftype != ftype:
                    wrong_type_fields.append(f"{doc_fname} ({doc_ftype}, asteptat {ftype})")
            if wrong_type_fields:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=tmpl_info["name"],
                        fid=0,
                        reason=(
                            f"Tip de date gresit fata de sablon ({len(wrong_type_fields)}): "
                            f"{', '.join(wrong_type_fields[:MAX_REPORTED])}"
                        ),
                    )
                )

        template_ds = None
        doc_ds = None
        return failures
