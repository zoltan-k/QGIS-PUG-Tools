# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca datele temporale din zonele
functionale sunt aceleasi (toate inregistrarile dintr-o coloana trebuie sa
aiba aceeasi valoare de data, la nivelul intregului strat).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, request_for_fields


class ConsistentTemporalRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: [coloane_de_data_ce_trebuie_sa_coincida]}.
    """

    def __init__(self, name, rules, description="", rule_id=18):
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
        reference = {}
        counts = {c: 0 for c in columns}

        for feat in layer.getFeatures(request):
            for column in columns:
                if counts[column] >= MAX_REPORTED:
                    continue
                value = feat[column]

                if is_null(value):
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feat.id(),
                            reason=f"Coloana '{column}' nu are valoare (NULL/lipsa).",
                        )
                    )
                    counts[column] += 1
                    continue

                if column not in reference:
                    reference[column] = value
                    continue

                if value != reference[column]:
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feat.id(),
                            reason=(
                                f"Valoarea '{value}' din coloana '{column}' difera de "
                                f"valoarea de referinta '{reference[column]}' folosita "
                                "in restul stratului."
                            ),
                        )
                    )
                    counts[column] += 1

        return failures

    def run(self, project):
        all_failures = []
        for layer_name, columns in self.rules.items():
            all_failures.extend(self._validate_layer(project, layer_name, columns))
        return all_failures
