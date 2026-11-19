# -*- coding: utf-8 -*-
"""
Setari ale plugin-ului persistate prin QgsSettings (profilul QGIS curent),
separate de tools/template_paths.py (care gestioneaza doar sablonul).
"""

from qgis.core import QgsSettings

# Toleranta stricta (sub care o geometrie trece fara nicio observatie) NU e
# configurabila - valoarea publicata de validatorul oficial. Doar pragul
# superior (peste care esecul devine BLOCKER in loc de WARNING) e ajustabil.
BOUNDARY_BUFFER_STRICT_M = 0.1
BOUNDARY_BUFFER_DEFAULT_M = 10.0
_BOUNDARY_BUFFER_KEY = "PUGTools/boundary_buffer_m"


def get_boundary_buffer_m():
    """
    Toleranta (in metri) folosita de regulile 26/27 pentru zona de
    "avertizare" (geometrie in afara limitei stricte de 0.1 m, dar inca in
    interiorul acestei tolerante - warning, nu esec). Implicit 10 m, conform
    precizarilor tehnice OMDLPA 904 (buffer(10) in validatorul oficial).
    """
    settings = QgsSettings()
    value = settings.value(_BOUNDARY_BUFFER_KEY, BOUNDARY_BUFFER_DEFAULT_M, type=float)
    # niciodata sub pragul strict - ar inversa sensul intervalului avertizare/esec.
    return max(value, BOUNDARY_BUFFER_STRICT_M)


def set_boundary_buffer_m(value):
    settings = QgsSettings()
    settings.setValue(_BOUNDARY_BUFFER_KEY, float(value))


# Copie locala a GPKG-ului pe durata validarii (vezi validations/gpkg_utils.py:
# local_copy_session). "auto" = doar daca proiectul sta pe o unitate de retea.
LOCAL_COPY_MODES = ("auto", "always", "never")
LOCAL_COPY_DEFAULT = "auto"
_LOCAL_COPY_KEY = "PUGTools/validation_local_copy"


def get_local_copy_mode():
    settings = QgsSettings()
    value = str(settings.value(_LOCAL_COPY_KEY, LOCAL_COPY_DEFAULT)).strip().lower()
    return value if value in LOCAL_COPY_MODES else LOCAL_COPY_DEFAULT


def set_local_copy_mode(value):
    if value not in LOCAL_COPY_MODES:
        raise ValueError(f"Mod invalid pentru copia locala: {value!r}")
    settings = QgsSettings()
    settings.setValue(_LOCAL_COPY_KEY, value)
