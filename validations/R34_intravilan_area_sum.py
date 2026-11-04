# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca suma ariilor din coloana ArieINT a
stratului LimitaIntravilanPropusa este egala cu aria din coloana ArieINT a
stratului PlanSpatial (toleranta 0.1 ha). PlanSpatial trebuie sa contina
exact o singura entitate.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import get_layer, is_null, request_for_fields

TOLERANCE = 0.1


class IntravilanAreaSumRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict {"PlanSpatial": camp_arie, "LimitaIntravilanPropusa": camp_arie}.
    """

    def __init__(self, name, rules, description="", rule_id=34):
        super().__init__(name, description, rule_id)
        self.planspatial_layer_name = "PlanSpatial"
        self.propusa_layer_name = "LimitaIntravilanPropusa"
        self.planspatial_field = rules[self.planspatial_layer_name]
        self.propusa_field = rules[self.propusa_layer_name]

    def run(self, project):
        ps_layer = get_layer(project, self.planspatial_layer_name)
        propusa_layer = get_layer(project, self.propusa_layer_name)

        if ps_layer.featureCount() != 1:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.planspatial_layer_name,
                    fid=0,
                    reason=(
                        f"Stratul '{self.planspatial_layer_name}' trebuie sa contina "
                        f"exact o singura entitate (are {ps_layer.featureCount()})."
                    ),
                )
            ]

        ps_feat = next(ps_layer.getFeatures(request_for_fields(ps_layer, [self.planspatial_field])))
        reference_value = ps_feat[self.planspatial_field]
        if is_null(reference_value):
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.planspatial_layer_name,
                    fid=ps_feat.id(),
                    reason=f"Coloana '{self.planspatial_field}' nu are valoare (NULL/lipsa).",
                )
            ]

        total = 0.0
        request = request_for_fields(propusa_layer, [self.propusa_field])
        for feat in propusa_layer.getFeatures(request):
            value = feat[self.propusa_field]
            if not is_null(value):
                total += float(value)

        if abs(total - float(reference_value)) > TOLERANCE:
            return [
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=self.propusa_layer_name,
                    fid=0,
                    reason=(
                        f"Suma coloanei '{self.propusa_field}' din "
                        f"'{self.propusa_layer_name}' ({total:.2f} ha) difera de "
                        f"'{self.planspatial_layer_name}.{self.planspatial_field}' "
                        f"({float(reference_value):.2f} ha) cu mai mult decat toleranta "
                        f"de {TOLERANCE} ha."
                    ),
                )
            ]

        return []
