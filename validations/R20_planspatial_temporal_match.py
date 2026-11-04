# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca datele temporale din stratul
PlanSpatial coincid cu datele temporale din zonele functionale si zona de
reglementare suplimentara.

Stratul tinta (PlanSpatial) este citit o singura data si valoarea de
referinta este pusa in cache, pentru toate regulile care il refera - cache
LOCAL fiecarei rulari a run() (nu pe instanta), altfel o a doua rulare a
ACELEIASI instante de regula (deja inregistrata la nivel de modul, deci
reutilizata pentru toata sesiunea QGIS) ar continua sa foloseasca valoarea
citita la prima rulare, chiar daca PlanSpatial s-a modificat intre timp -
exact scenariul unei re-validari dupa o corectie (vezi tools/rule_fixes.py
si "Repara" din ui/results_dialog.py, care ruleaza din nou regulile pe
aceleasi instante dupa fiecare remediere aplicata).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, request_for_fields


class PlanSpatialTemporalMatchRule(BaseValidationRule):
    """
    Parametrul `rules` este o lista de dict-uri:
        {"layer": strat_tinta, "match_fields_from": {strat_sursa: camp_sursa}, "with_field": camp_tinta}
    """

    def __init__(self, name, rules, description="", rule_id=20):
        super().__init__(name, description, rule_id)
        self.rules = rules

    @staticmethod
    def _reference_value(project, target_cache, target_layer_name, target_field):
        key = (target_layer_name, target_field)
        if key in target_cache:
            return target_cache[key]

        target_layer = get_layer(project, target_layer_name)
        request = request_for_fields(target_layer, [target_field])
        feat = next(target_layer.getFeatures(request), None)
        value = None if feat is None else feat[target_field]
        target_cache[key] = value
        return value

    def _validate_single_rule(self, project, target_cache, rule):
        target_layer_name = rule["layer"]
        target_field = rule["with_field"]
        matches = rule["match_fields_from"]
        source_layer_name = next(iter(matches))
        source_field = matches[source_layer_name]

        failures = []
        try:
            source_layer = get_layer(project, source_layer_name)
        except ValueError:
            return failures
        if source_layer.featureCount() < 1:
            return failures

        if source_field not in {f.name() for f in source_layer.fields()}:
            return failures

        reference_value = self._reference_value(project, target_cache, target_layer_name, target_field)

        request = request_for_fields(source_layer, [source_field])
        count = 0
        for feat in source_layer.getFeatures(request):
            if count >= MAX_REPORTED:
                break
            value = feat[source_field]
            if is_null(value) or is_null(reference_value) or value != reference_value:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=source_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"'{source_field}'={value!r} nu coincide cu "
                            f"'{target_layer_name}.{target_field}'={reference_value!r}."
                        ),
                    )
                )
                count += 1

        return failures

    def run(self, project):
        target_cache = {}
        all_failures = []
        for rule in self.rules:
            all_failures.extend(self._validate_single_rule(project, target_cache, rule))
        return all_failures
