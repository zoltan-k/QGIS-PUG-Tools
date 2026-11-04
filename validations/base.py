# -*- coding: utf-8 -*-
"""
Clasa de baza pentru regulile de validare si structura folosita pentru a
raporta o inregistrare esuata.

Orice regula noua trebuie sa:
    1. Mosteneasca BaseValidationRule si sa implementeze run(project).
    2. Returneze din run() o lista de obiecte ValidationFailure.
    3. Fie inregistrata (vezi validations/registry.py) intr-un modul de
       configurare (ex. rules_config.py), fara a fi nevoie sa modifici
       plugin.py sau restul plugin-ului.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationFailure:
    """
    O singura inregistrare care a esuat o regula de validare.

    `severity`, daca e setat ("BLOCKER" sau "WARNING"), suprascrie pentru
    ACEST esec severitatea implicita a regulii - folosit de reguli care pot
    produce esecuri de severitate diferita in functie de caz (ex. R26/R27:
    o geometrie usor in afara limitei stricte, dar inca in toleranta
    configurabila, e WARNING; una clar in afara e BLOCKER). Daca None (cazul
    obisnuit), UI-ul foloseste severitatea regulii (BaseValidationRule.severity).
    """

    rule_name: str
    layer_name: str
    fid: int
    reason: str
    severity: Optional[str] = None


class BaseValidationRule:
    """
    Interfata comuna pentru toate regulile de validare.

    `name` si `description` sunt folosite doar pentru afisare in rezultate.

    `severity` este "BLOCKER" sau "WARNING" (vezi tipul de alerta publicat
    pentru fiecare regula). Implicit este "BLOCKER"; pentru o regula de tip
    WARNING (ex. regula 30), suprascrie atributul pe instanta dupa
    construire, in rules_config.py: `instanta.severity = "WARNING"`.
    """

    severity = "BLOCKER"

    def __init__(self, name, description="", rule_id : int = 0):
        self.name = name
        self.description = description
        self.rule_id = rule_id

    def run(self, project):
        """
        Executa validarea pe baza proiectului QGIS activ (instanta QgsProject).

        Trebuie sa returneze o lista de ValidationFailure (poate fi goala
        daca nu exista erori). In caz de eroare de configurare (strat sau
        camp lipsa etc.) se recomanda sa arunce o exceptie cu un mesaj clar;
        plugin-ul o va prinde si o va afisa in raportul de rulare, fara sa
        opreasca celelalte reguli inregistrate.
        """
        raise NotImplementedError("Metoda run() trebuie implementata de subclase.")
