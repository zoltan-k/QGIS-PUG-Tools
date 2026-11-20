# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica coloanele straturilor din fisierul GPKG sa
contina date.

Pentru fiecare strat din `rules` (dict strat -> lista de coloane
obligatorii): daca stratul nu contine nicio inregistrare, este raportat ca
strat gol (nu se mai verifica si coloanele). Altfel, pentru fiecare coloana
obligatorie se colecteaza FID-urile inregistrarilor cu valoare NULL/lipsa
(maxim MAX_REPORTED per coloana).
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, request_for_fields


def _is_missing(value):
    """NULL, sau text gol / doar spatii (ca in R13/R14)."""
    return is_null(value) or (isinstance(value, str) and not value.strip())


class ColumnDataRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {nume_strat: [coloane_obligatorii]}; un
    element poate fi si un tuple/lista de coloane = grup "sau" (cel putin una
    completata, ex. ("POT", "POT_detaliu")), sau un dict {"any_of": [[...], ...]}
    (kit 3.1.1, pachet 2026.11.13): o inregistrare cade DOAR daca TOATE coloanele
    din TOATE perechile sunt goale (NULL/lipsa/doar spatii); perechile necompletate
    in unele inregistrari nu sunt raportate. 0 si "Nu este cazul" conteaza ca
    completate. O coloana obligatorie care lipseste din strat este raportata ca
    esec (nu ignorata), cu exceptia celor din `optional` ({strat: [coloane]}) -
    coloane pe care documentatia le poate omite (vezi regula 10).
    """

    def __init__(self, name, rules, description="", rule_id=12, optional=None):
        super().__init__(name, description, rule_id)
        self.rules = rules
        self.optional = {k: set(v) for k, v in (optional or {}).items()}

    def _validate_layer(self, project, layer_name, columns):
        failures = []
        layer = get_layer(project, layer_name)

        if layer.featureCount() < 1:
            failures.append(
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=layer_name,
                    fid=0,
                    reason=f"Stratul {layer_name} nu contine date",
                )
            )
            return failures

        field_names = {f.name() for f in layer.fields()}

        for column in columns:
            if isinstance(column, dict):
                failures.extend(self._validate_any_of(layer, layer_name, column["any_of"], field_names))
                continue
            if isinstance(column, (tuple, list)):
                failures.extend(self._validate_group(layer, layer_name, column, field_names))
                continue
            if column not in field_names:
                failures.append(self._missing_column_failure(layer_name, column))
                continue
            count = 0
            request = request_for_fields(layer, [column])
            for feat in layer.getFeatures(request):
                if count >= MAX_REPORTED:
                    break
                if _is_missing(feat[column]):
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feat.id(),
                            reason=f"Coloana '{column}' nu are valoare (NULL/lipsa).",
                        )
                    )
                    count += 1

        return failures

    def _missing_column_failure(self, layer_name, column):
        return ValidationFailure(
            rule_name=self.name,
            layer_name=layer_name,
            fid=0,
            reason=f"Coloana obligatorie '{column}' lipseste din stratul {layer_name}.",
        )

    def _validate_any_of(self, layer, layer_name, pairs, field_names):
        """
        Grup "any_of" (kit 3.1.1): coloanele din toate perechile sunt tratate
        impreuna; o inregistrare cade doar daca toate sunt goale. Coloanele
        lipsa din strat sunt raportate, mai putin cele optionale (dar cel putin
        o coloana trebuie sa existe).
        """
        all_columns = [c for pair in pairs for c in pair]
        optional = self.optional.get(layer_name, set())
        failures = [
            self._missing_column_failure(layer_name, c)
            for c in all_columns
            if c not in field_names and c not in optional
        ]
        present = [c for c in all_columns if c in field_names]
        if not present:
            return failures
        label = ", ".join(present)
        count = 0
        request = request_for_fields(layer, present)
        for feat in layer.getFeatures(request):
            if count >= MAX_REPORTED:
                break
            if all(_is_missing(feat[c]) for c in present):
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feat.id(),
                        reason=f"Toate coloanele ({label}) sunt goale (cel putin una trebuie completata).",
                    )
                )
                count += 1
        return failures

    def _validate_group(self, layer, layer_name, group, field_names):
        """
        Grup "sau" de coloane (ex. ("POT", "POT_detaliu")): fiecare inregistrare
        trebuie sa aiba valoare in CEL PUTIN una dintre ele (kit de validare
        3.0.4+). Toate coloanele grupului trebuie sa existe in strat.
        """
        failures = []
        missing = [c for c in group if c not in field_names]
        if missing:
            return [self._missing_column_failure(layer_name, c) for c in missing]
        label = " / ".join(group)
        count = 0
        request = request_for_fields(layer, list(group))
        for feat in layer.getFeatures(request):
            if count >= MAX_REPORTED:
                break
            if all(_is_missing(feat[c]) for c in group):
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=layer_name,
                        fid=feat.id(),
                        reason=f"Niciuna dintre coloanele '{label}' nu are valoare (cel putin una trebuie completata).",
                    )
                )
                count += 1
        return failures

    def run(self, project):
        all_failures = []
        for layer_name, columns in self.rules.items():
            all_failures.extend(self._validate_layer(project, layer_name, columns))
        return all_failures
