# -*- coding: utf-8 -*-
"""
Regula de validare: detectie sliver polygons (poligoane degenerate / benzi
inguste), folosind GDAL/OGR direct pe fisierul .gpkg. Calea fisierului este
dedusa din sursa unui strat deja incarcat in proiectul QGIS activ.

Definitie conforma kitului de validare 3.0.4+ (un avertisment, nu motiv de
respingere): drumurile si apele NU mai sunt semnalate doar pentru ca sunt lungi
si inguste. Se semnaleaza, pentru fiecare PARTE a unui MultiPolygon (inclusiv
geometriile cu coordonate Z):
    - latime < 1 m, indiferent de lungime;
    - latime < 3 m SI lungime >= 3 x latime;
    - arie practic nula (< 1e-6).
Latimea/lungimea sunt cele ale dreptunghiului echivalent al inelului exterior
(aceeasi arie si acelasi perimetru): L + l = P/2, L * l = A - acuratete buna
pentru benzi, indiferent de orientarea lor (nu depinde de bounding box).
"""

import math

from osgeo import ogr

from .base import BaseValidationRule, ValidationFailure
from .gpkg_utils import MAX_REPORTED

AREA_MIN_THRESHOLD = 1e-6
HARD_WIDTH_M = 1.0
SOFT_WIDTH_M = 3.0
MIN_ELONGATION = 3.0


class SliverPolygonRule(BaseValidationRule):
    """
    Parametrul `valoare_regula` este un string cu nume de straturi separate
    prin virgula, ex: "ZFExistenta,ZFPropusa".
    """

    def __init__(self, name, valoare_regula, description="", rule_id=30):
        super().__init__(name, description, rule_id)
        self.layer_names = [n.strip() for n in valoare_regula.split(",") if n.strip()]

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _find_gpkg_path(project, layer_name):
        layers = project.mapLayersByName(layer_name)
        if not layers:
            raise ValueError(f"Stratul '{layer_name}' nu a fost gasit in proiect.")
        if len(layers) > 1:
            raise ValueError(
                f"Exista mai multe straturi cu numele '{layer_name}' in proiect."
            )
        source = layers[0].source()
        return source.split("|")[0]

    @staticmethod
    def _equivalent_rectangle(part):
        """(latime, lungime, arie) ale dreptunghiului echivalent inelului exterior."""
        ring = part.GetGeometryRef(0)
        if ring is None:
            return 0.0, 0.0, 0.0
        outer = ogr.Geometry(ogr.wkbPolygon)
        outer.AddGeometry(ring.Clone())
        area = outer.GetArea()
        perimeter = ring.Length()
        half = perimeter / 2.0
        disc = half * half - 4.0 * area
        if disc < 0:  # forma foarte compacta (ex. patrat/cerc) - nu e banda
            side = perimeter / 4.0
            return side, side, area
        root = math.sqrt(disc)
        return (half - root) / 2.0, (half + root) / 2.0, area

    @classmethod
    def _classify_sliver(cls, geom):
        """(True, motiv) la prima parte care e sliver, altfel (False, None)."""
        flat = ogr.GT_Flatten(geom.GetGeometryType())
        parts = (
            [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
            if flat == ogr.wkbMultiPolygon
            else [geom]
        )
        for index, part in enumerate(parts, start=1):
            if part is None or part.IsEmpty():
                continue
            width, length, area = cls._equivalent_rectangle(part)
            label = f"partea {index}: " if len(parts) > 1 else ""
            if area < AREA_MIN_THRESHOLD:
                return True, f"{label}arie practic nula ({area:.3e}) - poligon degenerat."
            if width < HARD_WIDTH_M:
                return True, (
                    f"{label}latime ~{width:.2f} m (< {HARD_WIDTH_M:g} m), lungime ~{length:.2f} m "
                    "- zona prea ingusta, indiferent de lungime."
                )
            if width < SOFT_WIDTH_M and length >= MIN_ELONGATION * width:
                return True, (
                    f"{label}latime ~{width:.2f} m (< {SOFT_WIDTH_M:g} m) si lungime ~{length:.2f} m "
                    f"(>= {MIN_ELONGATION:g} x latimea) - fasie ingusta."
                )
        return False, None

    # -- core logic ------------------------------------------------------------

    def run(self, project):
        failures = []

        for layer_name in self.layer_names:
            gpkg_path = self._find_gpkg_path(project, layer_name)

            ds = ogr.Open(gpkg_path, 0)  # 0 = read-only
            if ds is None:
                raise RuntimeError(f"Nu s-a putut deschide fisierul GPKG: {gpkg_path}")

            ogr_layer = ds.GetLayerByName(layer_name)
            if ogr_layer is None:
                raise ValueError(
                    f"Stratul '{layer_name}' nu a fost gasit in fisierul '{gpkg_path}'."
                )

            ogr_layer.ResetReading()
            for feature in ogr_layer:
                geom = feature.GetGeometryRef()
                if geom is None:
                    continue

                flat_type = ogr.GT_Flatten(geom.GetGeometryType())
                if flat_type not in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
                    continue

                if sum(1 for f in failures if f.layer_name == layer_name) >= MAX_REPORTED:
                    break
                is_sliver, reason = self._classify_sliver(geom)
                if is_sliver:
                    failures.append(
                        ValidationFailure(
                            rule_name=self.name,
                            layer_name=layer_name,
                            fid=feature.GetFID(),
                            reason=reason,
                        )
                    )

            ds = None  # inchide sursa OGR

        return failures
