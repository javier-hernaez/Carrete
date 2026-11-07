"""Carrete: reunir, ordenar y conservar las fotos y vídeos de un grupo de personas."""

import os

# La imagen de Docker fija CARRETE_VERSION al construirse (etiqueta o commit); en desarrollo, «dev».
__version__ = os.environ.get("CARRETE_VERSION", "dev")
