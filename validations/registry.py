# -*- coding: utf-8 -*-
"""
Registru simplu de reguli de validare.

Modulele de configurare (ex. rules_config.py) apeleaza register_rule() la
import pentru a-si inregistra instantele. Plugin-ul apeleaza doar
get_registered_rules() si nu are nevoie sa cunoasca regulile individuale.
"""

_REGISTERED_RULES = []


def register_rule(rule):
    """Inregistreaza o instanta de regula (BaseValidationRule) pentru rulare."""
    _REGISTERED_RULES.append(rule)
    return rule


def get_registered_rules():
    """Returneaza o copie a listei de reguli inregistrate, in ordinea adaugarii."""
    return list(_REGISTERED_RULES)


def clear_registry():
    """Utila mai ales in teste, pentru a reseta registrul intre rulari."""
    _REGISTERED_RULES.clear()
