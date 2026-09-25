"""Errores del radar.

Cada error lleva un mensaje pensado para una persona que no programa. La traza técnica
va al detalle, nunca a la pantalla del usuario.
"""


class ErrorRadar(Exception):
    def __init__(self, mensaje: str, detalle: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle

    def __str__(self) -> str:
        return self.mensaje


class SinConexion(ErrorRadar):
    """No hay red."""


class CertificadoNoVerificable(ErrorRadar):
    """El certificado del servidor no se puede verificar. Nunca se desactiva la verificación."""


class FuenteNoResponde(ErrorRadar):
    """La Plataforma de Contratación devuelve error o no contesta."""


class DocumentoIlegible(ErrorRadar):
    """El pliego no se puede leer: dañado, vacío o en un formato que no abrimos."""


class FaltaConfiguracion(ErrorRadar):
    """Falta una variable en el fichero .env."""
