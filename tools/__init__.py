# -*- coding: utf-8 -*-


def save_style_to_database(layer, name, description, use_as_default, ui_file_content):
    """
    QgsMapLayer.saveStyleToDatabase() e deprecat in favoarea
    saveStyleToDatabaseV2() - disponibila doar in build-uri QGIS recente,
    inca neprezenta in versiunea minima declarata a plugin-ului
    (qgisMinimumVersion, vezi metadata.txt). Foloseste varianta noua daca
    exista, altfel varianta veche (fara warning pe QGIS recent, fara sa
    ridice minimul de compatibilitate).

    Returneaza mesajul de eroare (string gol daca a reusit) - apelantii care
    nu au nevoie sa verifice pot ignora valoarea returnata, ca pana acum.
    """
    if hasattr(layer, "saveStyleToDatabaseV2"):
        _flags, msg_error = layer.saveStyleToDatabaseV2(name, description, use_as_default, ui_file_content)
        return msg_error
    return layer.saveStyleToDatabase(name, description, use_as_default, ui_file_content)
