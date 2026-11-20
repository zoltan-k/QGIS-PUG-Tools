# -*- coding: utf-8 -*-
"""
Regula de validare (kit 3.1.1, pachet 2026.11.13): codurile din
RegulamentLocalUrbanism si RegulamentLocalUrbanismDetaliat (si tipul
Tip_SZF_ZRS_D din RLUD) trebuie sa fie unice, iar tipul si tipul zonei din
RegulamentLocalUrbanism trebuie sa corespunda codului din nomenclatorul
"sys_zona" (cod, definitie, tip_zona).

Parametrul `rules` este un dict {strat: {"unique": [coloane], "type_of":
{coloana_cod: [coloana_tip, coloana_tip_zona]}}} (cheia "type_of" e optionala).

- Unicitate: raporteaza valorile duplicate (nu FID-uri), independent pentru
  fiecare coloana din "unique" (cel mult MAX_REPORTED). In RLU doar codul trebuie
  sa fie unic - coduri diferite pot avea acelasi tip (ZF07 si ZRS07: "Zona
  centrala").
- Tip corespunzator codului: pentru fiecare inregistrare din RLU se verifica ca
  exista un cod, ca se afla in "sys_zona", ca Tip_ZF_ZRS == definitie si ca
  Tip_zona == tip_zona. Spatiile de la inceput/sfarsit si cele duble se ignora.
  Raportat: inregistrari fara cod, coduri necunoscute, tipuri incorecte.
"""

import re

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, get_layer_or_open, is_null, request_for_fields

ZONA_LAYER = "sys_zona"


def _norm(value):
    """Taie spatiile de la capete si comprima spatiile duble (None/NULL -> '')."""
    if is_null(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


class UniqueValuesRule(BaseValidationRule):
    """
    Parametrul `rules`: vezi docstring-ul modulului.
    """

    def __init__(self, name, rules, description="", rule_id=17):
        super().__init__(name, description, rule_id)
        self.rules = rules

    def _validate_layer(self, project, layer_name, spec):
        columns = spec["unique"]
        failures = []
        try:
            layer = get_layer(project, layer_name)
        except ValueError:
            return failures
        if layer.featureCount() < 1:
            return failures

        field_names = {f.name() for f in layer.fields()}
        columns = [c for c in columns if c in field_names]
        if not columns:
            return failures

        request = request_for_fields(layer, columns)
        seen = {c: set() for c in columns}
        duplicates = {c: [] for c in columns}

        for feat in layer.getFeatures(request):
            for column in columns:
                value = feat[column]
                if is_null(value):
                    continue
                if value in seen[column]:
                    if len(duplicates[column]) < MAX_REPORTED:
                        duplicates[column].append(value)
                else:
                    seen[column].add(value)

        for column in columns:
            for value in duplicates[column]:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=0,
                        reason=f"Valoarea duplicata '{value}' in coloana '{column}'.",
                    )
                )

        for code_col, (type_col, zone_type_col) in spec.get("type_of", {}).items():
            failures.extend(self._validate_types(project, layer, layer_name, code_col, type_col, zone_type_col))

        return failures

    def _validate_types(self, project, layer, layer_name, code_col, type_col, zone_type_col):
        field_names = {f.name() for f in layer.fields()}
        if not {code_col, type_col, zone_type_col} <= field_names:
            return []
        try:
            zona = get_layer_or_open(project, ZONA_LAYER)
        except ValueError as exc:
            return [ValidationFailure(rule_name=self.name, layer_name=layer_name, fid=0, reason=str(exc))]
        nomenclature = {}
        for feat in zona.getFeatures():
            code = _norm(feat["cod"])
            if code:
                nomenclature[code] = (_norm(feat["definitie"]), _norm(feat["tip_zona"]))

        no_code, unknown, wrong = [], {}, {}
        request = request_for_fields(layer, [code_col, type_col, zone_type_col])
        for feat in layer.getFeatures(request):
            code = _norm(feat[code_col])
            if not code:
                no_code.append(feat.id())
                continue
            expected = nomenclature.get(code)
            if expected is None:
                unknown.setdefault(code, []).append(feat.id())
                continue
            for col, found, exp in (
                (type_col, _norm(feat[type_col]), expected[0]),
                (zone_type_col, _norm(feat[zone_type_col]), expected[1]),
            ):
                if found != exp:
                    wrong.setdefault((code, col, found, exp), []).append(feat.id())

        failures = []
        for fid in no_code[:MAX_REPORTED]:
            failures.append(ValidationFailure(
                rule_name=self.name, layer_name=layer_name, fid=fid,
                reason=f"Inregistrare fara cod in coloana '{code_col}'."))
        for code, fids in list(unknown.items())[:MAX_REPORTED]:
            failures.append(ValidationFailure(
                rule_name=self.name, layer_name=layer_name, fid=fids[0],
                reason=f"Codul '{code}' din coloana '{code_col}' nu exista in nomenclatorul {ZONA_LAYER} "
                       f"(FID: {', '.join(map(str, fids[:MAX_REPORTED]))})."))
        for (code, col, found, exp), fids in list(wrong.items())[:MAX_REPORTED]:
            failures.append(ValidationFailure(
                rule_name=self.name, layer_name=layer_name, fid=fids[0],
                reason=f"Cod '{code}': valoarea '{found}' din '{col}' nu corespunde nomenclatorului "
                       f"(asteptat '{exp}'; FID: {', '.join(map(str, fids[:MAX_REPORTED]))})."))
        return failures

    def run(self, project):
        all_failures = []
        for layer_name, spec in self.rules.items():
            all_failures.extend(self._validate_layer(project, layer_name, spec))
        return all_failures
