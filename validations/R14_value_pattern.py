# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica structura valorilor din coloanele
straturilor din fisierul GPKG sa fie conform cu structura valorilor din
OMDLPA 904 (validare prin expresii regulate, cu fullmatch).
"""

import re

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, normalize_date_text, request_for_fields


class ValuePatternRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {strat: [{"columns": [...], "match": regex}, ...]}.
    O coloana poate aparea in mai multe grupuri; e valida daca respecta
    fullmatch pe cel putin unul dintre pattern-urile asociate.
    """

    def __init__(self, name, rules, description="", rule_id=14):
        super().__init__(name, description, rule_id)
        self.rules = rules

    @staticmethod
    def _to_text(value):
        text = normalize_date_text(value)
        if text is not None:
            return text
        return str(value)

    def _validate_layer(self, project, layer_name, groups):
        failures = []
        try:
            layer = get_layer(project, layer_name)
        except ValueError:
            return failures
        if layer.featureCount() < 1:
            return failures

        field_names = {f.name() for f in layer.fields()}

        column_patterns = {}
        for group in groups:
            pattern = re.compile(group["match"])
            for column in group["columns"]:
                if column not in field_names:
                    continue
                column_patterns.setdefault(column, []).append(pattern)

        if not column_patterns:
            return failures

        columns = list(column_patterns.keys())
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

                text = self._to_text(value)
                if not any(p.fullmatch(text) for p in column_patterns[column]):
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feat.id(),
                            reason=(
                                f"Valoarea '{text}' din coloana '{column}' nu respecta "
                                "formatul asteptat conform OMDLPA 904."
                            ),
                        )
                    )
                    counts[column] += 1

        return failures

    def run(self, project):
        all_failures = []
        for layer_name, groups in self.rules.items():
            all_failures.extend(self._validate_layer(project, layer_name, groups))
        return all_failures
