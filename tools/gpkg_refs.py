# -*- coding: utf-8 -*-
"""
Ce fisiere .gpkg sunt "folosite" de un proiect QGIS si care sunt "orfane".

Dupa "Consolideaza straturile" (tools/gpkg_consolidator.py), fisierele GPKG
din care au fost mutate straturile raman pe disc (unealta nu sterge nimic),
dar nu mai sunt referite de niciun strat al proiectului. Copia portabila,
copiile de rezerva si "Pregateste proiectul pentru validare oficiala" trebuie
sa le ignore: un .gpkg aflat in folderul pachetului pe care NICIUN strat al
proiectului nu il mai refera este considerat orfan si nu este inclus.

Garda de siguranta: nimic nu este exclus cand proiectul nu refera niciun
.gpkg din folderul respectiv (ex. proiect gol/invalid) - altfel o eroare de
detectie ar goli copia de rezerva.
"""

import os

from qgis.PyQt.QtCore import QUrl
from qgis.core import QgsProject, QgsProviderRegistry

SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def norm_path(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _is_inside(path, folder):
    path, folder = norm_path(path), norm_path(folder)
    return path == folder or path.startswith(folder + os.sep)


def layer_gpkg_path(layer):
    """Calea absoluta (neformatata) a unui fisier .gpkg referit de strat, sau None."""
    try:
        provider = layer.providerType()
        source = layer.source()
    except AttributeError:
        return None
    if provider in ("memory", "virtual"):
        return None
    path = None
    try:
        parts = QgsProviderRegistry.instance().decodeUri(provider, source)
        if isinstance(parts, dict):
            path = parts.get("path")
    except Exception:  # noqa: BLE001
        path = None
    if not path:
        path = source.split("|")[0]
    if path and path.lower().endswith(".gpkg") and os.path.isabs(path):
        return path
    return None


def _virtual_source_paths(layer):
    """Caile .gpkg referite direct (dupa cale) de un strat virtual, daca exista."""
    out = []
    try:
        if layer.providerType() != "virtual":
            return out
        from qgis.core import QgsVirtualLayerDefinition
        definition = QgsVirtualLayerDefinition.fromUrl(QUrl.fromEncoded(layer.source().encode()))
        for src in definition.sourceLayers():
            if src.isReferenced():
                continue
            path = src.source().split("|")[0]
            if path.lower().endswith(".gpkg"):
                out.append(path)
    except Exception:  # noqa: BLE001
        pass
    return out


def referenced_gpkgs(project=None):
    """Multimea cailor normalizate ale fisierelor .gpkg referite de straturile proiectului (si cele invalide)."""
    project = project or QgsProject.instance()
    found = set()
    for layer in project.mapLayers().values():
        path = layer_gpkg_path(layer)
        if path:
            found.add(norm_path(path))
        for vpath in _virtual_source_paths(layer):
            found.add(norm_path(vpath))
    return found


def orphaned_files(folder, project=None, referenced=None):
    """
    Cai absolute (normalizate) ale fisierelor care NU trebuie incluse din
    `folder`: orice .gpkg pe care proiectul nu il mai refera, plus fisierele
    lui -wal/-shm/-journal. Set gol daca proiectul nu refera niciun .gpkg din
    `folder` (garda de siguranta).
    """
    if not folder or not os.path.isdir(folder):
        return set()
    if referenced is None:
        referenced = referenced_gpkgs(project)
    if not any(_is_inside(p, folder) for p in referenced):
        return set()
    excluded = set()
    for root, _dirs, files in os.walk(folder):
        for fname in files:
            if not fname.lower().endswith(".gpkg"):
                continue
            full = os.path.join(root, fname)
            if norm_path(full) in referenced:
                continue
            excluded.add(norm_path(full))
            for suffix in SIDECAR_SUFFIXES:
                excluded.add(norm_path(full + suffix))
    return excluded
