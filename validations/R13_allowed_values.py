# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica valorile din coloanele straturilor din
fisierul GPKG sa fie conforme cu valorile din OMDLPA 904.

Fiecare coloana verificata este asociata (prin cheia "match") cu o lista de
valori valide, preluata dintr-un tabel de referinta ("_..." ) inclus in
sablonul GPKG. MATCH_KEY_SOURCES de mai jos este dedusa din tabelele de
referinta livrate cu sablonul (vezi templates/.../*.gpkg), intrucat
structura interna "template_metadata" a validatorului oficial nu este
publicata.

Cache-ul valorilor admise per "match" este LOCAL fiecarei rulari a run()
(nu pe instanta), altfel o a doua rulare a ACELEIASI instante de regula
(deja inregistrata la nivel de modul, deci reutilizata pentru toata sesiunea
QGIS) ar continua sa foloseasca valorile citite la prima rulare, chiar daca
tabelele de referinta s-au schimbat intre timp (ex. schimbarea sablonului
activ sau deschiderea altui proiect).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, field_value_set, get_layer, get_layer_or_open, is_null, request_for_fields

MATCH_KEY_SOURCES = {
    "NivelPlan": ("_nivel_plan", "definitie"),
    "Cod_ZF_ZRS": ("_zona", "cod"),
    # "Tip_ZF_ZRS" e valoarea descriptiva a zonei/subzonei (ex. "Zonă centrală",
    # "Terenuri agricole"), stocata in coloanele Tip_ZF/Tip_ZRS/Tip_ZF_ZRS - vine
    # din "_zona.definitie" (51 valori posibile), NU din "_tip_zona.definitie"
    # (doar 2 valori generice: "Zonă funcțională"/"Zonă de reglementare
    # suplimentară / de restricții" - acela e mapat separat la cheia "TipZona",
    # folosita pentru RegulamentLocalUrbanism.Tip_zona). Confirmat gresit
    # impotriva unui proiect PUG real, unde ~295 inregistrari valide erau
    # respinse din cauza acestei mapari incorecte.
    "Tip_ZF_ZRS": ("_zona", "definitie"),
    "Hilucs": ("_hilucs", "cod"),
    "TipZona": ("_tip_zona", "definitie"),
    "TipSubzona": ("_tip_subzona", "definitie"),
    "TipRTE": ("_tip_rte", "definitie"),
    "SubtipRTE": ("_subtip_rte", "definitie"),
    "StadiuRTE": ("_stadiu_rte", "definitie"),
    "TipCCom": ("_tip_ccom", "definitie"),
    "SubtipCCom": ("_subtip_ccom", "definitie"),
    "StadiuCCom": ("_stadiu_ccom", "definitie"),
    "TipRU": ("_tip_ru", "definitie"),
}


class AllowedValuesRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: [{"columns": [...], "match": cheie}, ...]}.
    """

    def __init__(self, name, rules, description="", rule_id=13):
        super().__init__(name, description, rule_id)
        self.rules = rules

    @staticmethod
    def _valid_values_for(project, match_cache, match_key):
        if match_key in match_cache:
            return match_cache[match_key]

        if match_key not in MATCH_KEY_SOURCES:
            raise ValueError(
                f"Cheia de referinta '{match_key}' nu este definita in MATCH_KEY_SOURCES."
            )
        ref_layer_name, ref_field = MATCH_KEY_SOURCES[match_key]
        ref_layer = get_layer_or_open(project, ref_layer_name)
        values = {
            v.strip() if isinstance(v, str) else v
            for v in field_value_set(ref_layer, ref_field)
        }
        match_cache[match_key] = values
        return values

    def _validate_layer(self, project, match_cache, layer_name, groups):
        failures = []
        try:
            layer = get_layer(project, layer_name)
        except ValueError:
            return failures
        if layer.featureCount() < 1:
            return failures

        field_names = {f.name() for f in layer.fields()}

        column_valid_values = {}
        for group in groups:
            valid_values = self._valid_values_for(project, match_cache, group["match"])
            for column in group["columns"]:
                if column not in field_names:
                    continue
                column_valid_values.setdefault(column, set()).update(valid_values)

        if not column_valid_values:
            return failures

        columns = list(column_valid_values.keys())
        request = request_for_fields(layer, columns)
        counts = {c: 0 for c in columns}

        for feat in layer.getFeatures(request):
            for column in columns:
                if counts[column] >= MAX_REPORTED:
                    continue
                value = feat[column]
                if is_null(value) or (isinstance(value, str) and value.strip() == ""):
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feat.id(),
                            reason=f"Coloana '{column}' nu are valoare (NULL/gol).",
                        )
                    )
                    counts[column] += 1
                    continue

                comparable = value.strip() if isinstance(value, str) else value
                if comparable not in column_valid_values[column]:
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feat.id(),
                            reason=(
                                f"Valoarea '{value}' din coloana '{column}' nu se "
                                "regaseste in lista de valori admise (OMDLPA 904)."
                            ),
                        )
                    )
                    counts[column] += 1

        return failures

    def run(self, project):
        match_cache = {}
        all_failures = []
        for layer_name, groups in self.rules.items():
            all_failures.extend(self._validate_layer(project, match_cache, layer_name, groups))
        return all_failures
