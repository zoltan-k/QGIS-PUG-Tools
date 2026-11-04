# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca (cod, tip) din RegulamentLocalUrbanism
si RegulamentLocalUrbanismDetaliat sunt unice.

Raporteaza valorile duplicate (nu FID-uri), independent pentru fiecare
coloana - ca in definitia tehnica publicata.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, request_for_fields


class UniqueValuesRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: [coloane_ce_trebuie_sa_fie_unice]}.
    """

    def __init__(self, name, rules, description="", rule_id=17):
        super().__init__(name, description, rule_id)
        self.rules = rules

    def _validate_layer(self, project, layer_name, columns):
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

        return failures

    def run(self, project):
        all_failures = []
        for layer_name, columns in self.rules.items():
            all_failures.extend(self._validate_layer(project, layer_name, columns))
        return all_failures
