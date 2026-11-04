# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica straturile fisierul GPKG sa contina date
"""

from qgis.core import QgsFeatureRequest, NULL
from .base import BaseValidationRule, ValidationFailure


class LayerDataRule(BaseValidationRule):
    """
    Parametrul `rules` este o lista simpla cu numele straturilor obligatorii din GPKG,
    de verificat sa contina date.
    """

    def __init__(self, name, rules, description="", rule_id = 11):
        super().__init__(name, description, rule_id)
        self.rules = rules


    @staticmethod
    def _get_layer(project, layer_name):
        layers = project.mapLayersByName(layer_name)
        if not layers:
            raise ValueError(f"Stratul '{layer_name}' nu a fost gasit in proiect.")
        if len(layers) > 1:
            raise ValueError(
                f"Exista mai multe straturi cu numele '{layer_name}' in proiect; "
                "foloseste un identificator unic (layer id)."
            )
        return layers[0]


    # -- core logic ----------------------------------------------------------

    def _validate_single_rule(self, project, rule):
        layer_to_validate = self._get_layer(project,rule)
        failures = []
        if layer_to_validate.featureCount()<1:
            failures.append(
                ValidationFailure(
                    rule_name=self.name,
                    layer_name=rule,
                    reason=(
                        f"Stratul {rule} nu contine date"
                    ),
                    fid=0
                ),
            )
        return failures


    def run(self, project):
        all_failures = []
        for rule in self.rules:
            all_failures.extend(self._validate_single_rule(project, rule))
        return all_failures
