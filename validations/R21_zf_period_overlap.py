# -*- coding: utf-8 -*-
"""
Regula de validare: Se verifica perioada de timp din zonele functionale sa
nu se suprapuna si sa fie in ordine cronologica.

Pentru fiecare inregistrare din stratul tinta se verifica:
    1. ordinea cronologica: aprob_tinta <= exp_tinta;
    2. neaprapunerea cu intervalele din stratul sursa de referinta, folosind
       conditia standard target_aprob < source_exp AND target_exp > source_aprob.
"""

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED, get_layer, parse_date, request_for_fields


class ZFPeriodOverlapRule(BaseValidationRule):
    """
    Parametrul `rules` este un dict:
        {strat_tinta: {"match_fields_from": {strat_sursa: [camp_aprob, camp_exp]},
                        "with_field": [camp_aprob, camp_exp]}}
    """

    def __init__(self, name, rules, description="", rule_id=21):
        super().__init__(name, description, rule_id)
        self.rules = rules

    def _validate_single_rule(self, project, target_layer_name, config):
        failures = []
        matches = config["match_fields_from"]
        source_layer_name = next(iter(matches))
        source_aprob_field, source_exp_field = matches[source_layer_name]
        target_aprob_field, target_exp_field = config["with_field"]

        try:
            source_layer = get_layer(project, source_layer_name)
            target_layer = get_layer(project, target_layer_name)
        except ValueError:
            return failures

        existing_intervals = []
        request = request_for_fields(source_layer, [source_aprob_field, source_exp_field])
        for feat in source_layer.getFeatures(request):
            aprob = parse_date(feat[source_aprob_field])
            exp = parse_date(feat[source_exp_field])
            if aprob is not None and exp is not None:
                existing_intervals.append((aprob, exp))

        request = request_for_fields(target_layer, [target_aprob_field, target_exp_field])
        count = 0
        for feat in target_layer.getFeatures(request):
            if count >= MAX_REPORTED:
                break
            aprob = parse_date(feat[target_aprob_field])
            exp = parse_date(feat[target_exp_field])
            if aprob is None or exp is None:
                continue

            if aprob > exp:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=target_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"'{target_aprob_field}' ({aprob.isoformat()}) este ulterioara "
                            f"'{target_exp_field}' ({exp.isoformat()})."
                        ),
                    )
                )
                count += 1
                continue

            overlap = any(
                aprob < source_exp and exp > source_aprob
                for source_aprob, source_exp in existing_intervals
            )
            if overlap:
                failures.append(
                    ValidationFailure(
                        rule_name=self.name,
                        layer_name=target_layer_name,
                        fid=feat.id(),
                        reason=(
                            f"Intervalul [{aprob.isoformat()}, {exp.isoformat()}] se suprapune "
                            f"cu un interval existent din '{source_layer_name}'."
                        ),
                    )
                )
                count += 1

        return failures

    def run(self, project):
        all_failures = []
        for target_layer_name, config in self.rules.items():
            all_failures.extend(self._validate_single_rule(project, target_layer_name, config))
        return all_failures
