# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica daca combinatia de Cod si Tip dintr-un strat
de validat se regaseste in perechile valide construite din unul sau mai
multe straturi sursa.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, is_null, request_for_fields


class PairMembershipRule(BaseValidationRule):
    """
    Parametrul `rules` este o lista de dict-uri:
        {"validated_layer": strat, "validated_fields": [camp_cod, camp_tip],
         "valid_pairs_from": [{"layer": strat_sursa, "fields": [camp_cod, camp_tip]}, ...]}
    """

    def __init__(self, name, rules, description="", rule_id=22):
        super().__init__(name, description, rule_id)
        self.rules = rules

    def _build_valid_pairs(self, project, sources):
        pairs = set()
        for source in sources:
            try:
                layer = get_layer(project, source["layer"])
            except ValueError:
                continue
            cod_field, tip_field = source["fields"]
            field_names = {f.name() for f in layer.fields()}
            if cod_field not in field_names or tip_field not in field_names:
                continue
            request = request_for_fields(layer, [cod_field, tip_field])
            for feat in layer.getFeatures(request):
                cod, tip = feat[cod_field], feat[tip_field]
                if is_null(cod) or is_null(tip):
                    continue
                pairs.add((cod, tip))
        return pairs

    def _validate_single_rule(self, project, rule):
        failures = []
        validated_layer_name = rule["validated_layer"]
        cod_field, tip_field = rule["validated_fields"]

        try:
            layer = get_layer(project, validated_layer_name)
        except ValueError:
            return failures

        field_names = {f.name() for f in layer.fields()}
        if cod_field not in field_names or tip_field not in field_names:
            request = None
        else:
            request = request_for_fields(layer, [cod_field, tip_field])

        valid_pairs = self._build_valid_pairs(project, rule["valid_pairs_from"])

        if request is None:
            count = 0
            for feat in layer.getFeatures():
                if count >= MAX_REPORTED:
                    break
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=validated_layer_name,
                        fid=feat.id(),
                        reason=f"Campurile '{cod_field}'/'{tip_field}' lipsesc din schema stratului.",
                    )
                )
                count += 1
            return failures

        count = 0
        for feat in layer.getFeatures(request):
            if count >= MAX_REPORTED:
                break
            cod, tip = feat[cod_field], feat[tip_field]
            if is_null(cod) or is_null(tip):
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=validated_layer_name,
                        fid=feat.id(),
                        reason=f"Valoare NULL in campurile '{cod_field}'/'{tip_field}'.",
                    )
                )
                count += 1
                continue

            if (cod, tip) not in valid_pairs:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=validated_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"Perechea ('{cod}', '{tip}') nu se regaseste printre "
                            "perechile valide construite din straturile sursa."
                        ),
                    )
                )
                count += 1

        return failures

    def run(self, project):
        all_failures = []
        for rule in self.rules:
            all_failures.extend(self._validate_single_rule(project, rule))
        return all_failures
