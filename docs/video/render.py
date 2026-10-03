"""Renderiza el vídeo del radar: fotogramas con Pillow, narración ya generada, mp4 con ffmpeg.

    uv run --with pillow python render.py

No hay nada inventado: las cifras salen de la base del proyecto y de eval_resultados.
"""

from __future__ import annotations

import math
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).parent
W, H, FPS = 1920, 1080, 30
COLA = 0.45  # silencio al final de cada escena, para que respire

FONDO = (22, 24, 28)
PANEL = (30, 33, 38)
TINTA = (232, 230, 224)
APUNTE = (154, 161, 173)
REGLA = (51, 55, 63)
SELLO = (143, 176, 232)
OXIDO = (224, 147, 127)
VERDE = (143, 199, 164)

F = "C:/Windows/Fonts/"


def fuente(nombre: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(F + nombre, tam)


TITULO = fuente("segoeuib.ttf", 96)
TITULO_S = fuente("segoeuib.ttf", 68)
SERIF = fuente("georgia.ttf", 46)
SERIF_P = fuente("georgia.ttf", 38)
CUERPO = fuente("segoeui.ttf", 44)
CUERPO_N = fuente("segoeuib.ttf", 44)
PIE = fuente("segoeui.ttf", 40)
ETIQUETA = fuente("segoeuib.ttf", 26)
MONO = fuente("consola.ttf", 38)
MONO_G = fuente("consolab.ttf", 120)
MONO_M = fuente("consolab.ttf", 200)


def suave(x: float) -> float:
    """Aceleración y frenada. Nada entra ni sale de golpe: el vídeo no tiene cortes secos."""
    x = max(0.0, min(1.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


def entra(t: float, inicio: float, dura: float = 0.9) -> float:
    return suave((t - inicio) / dura)


def partir(texto: str, tipo, ancho: int) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = (actual + " " + palabra).strip()
        if tipo.getlength(prueba) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def escribir(d, xy, texto, tipo, color, alto=0, alfa=1.0, centrado=False, ancho=0):
    color = tuple(int(FONDO[i] + (color[i] - FONDO[i]) * alfa) for i in range(3))
    lineas = partir(texto, tipo, ancho) if ancho else [texto]
    x, y = xy
    salto = alto or int(tipo.size * 1.32)
    for linea in lineas:
        px = x - tipo.getlength(linea) / 2 if centrado else x
        d.text((px, y), linea, font=tipo, fill=color)
        y += salto
    return y


def caja(d, x, y, an, al, relleno=PANEL, borde=REGLA, r=8, alfa=1.0):
    relleno = tuple(int(FONDO[i] + (relleno[i] - FONDO[i]) * alfa) for i in range(3))
    borde = tuple(int(FONDO[i] + (borde[i] - FONDO[i]) * alfa) for i in range(3))
    d.rounded_rectangle([x, y, x + an, y + al], radius=r, fill=relleno, outline=borde, width=2)


def marco(d, rotulo: str, titular: str, t: float, ancho=1500):
    """La cabecera común: el rótulo del paso y el titular. Igual en todas las escenas."""
    a = entra(t, 0.1, 0.7)
    if a > 0:
        d.rectangle([160, 118, 160 + int(70 * a), 122], fill=SELLO)
        escribir(d, (160, 150), rotulo.upper(), ETIQUETA, SELLO, alfa=a)
    b = entra(t, 0.35, 0.9)
    if b > 0:
        tipo = TITULO if TITULO.getlength(titular) <= ancho else TITULO_S
        escribir(d, (160, 205 + int(18 * (1 - b))), titular, tipo, TINTA, alfa=b, ancho=ancho)


# --- Las escenas ------------------------------------------------------------------------


def escena_portada(d, t, dur):
    a = entra(t, 0.2, 1.0)
    if a > 0:
        d.rectangle([160, 300, 160 + int(180 * a), 306], fill=SELLO)
        escribir(d, (160, 340), "RADAR DE LICITACIONES", ETIQUETA, SELLO, alfa=a)
    b = entra(t, 0.6, 1.1)
    if b > 0:
        escribir(
            d,
            (160, 400 + int(24 * (1 - b))),
            "Un agente que lee el pliego",
            fuente("segoeuib.ttf", 130),
            TINTA,
            alfa=b,
        )
    c = entra(t, 1.4, 1.0)
    if c > 0:
        escribir(
            d,
            (160, 570),
            "y por qué no funcionó",
            fuente("georgiai.ttf", 96),
            SELLO,
            alfa=c,
        )
    e = entra(t, 3.0, 1.2)
    if e > 0:
        caja(d, 160, 730, 1100, 150, alfa=e)
        escribir(d, (200, 760), "Expediente 2024/PA/041 · Ayuntamiento de Pozuelo de Alarcón", MONO, APUNTE, alfa=e)
        escribir(d, (200, 812), "Emisión y venta de entradas · 93.472,31 €", SERIF_P, TINTA, alfa=e)


def escena_problema(d, t, dur):
    marco(d, "El día", "474 licitaciones nuevas cada día", t)
    # El enjambre: 474 puntos que aparecen uno a uno. Que se vea el volumen antes de contarlo.
    n = int(474 * suave(min(1.0, max(0.0, (t - 1.4) / 5.0))))
    for i in range(n):
        cx, cy = 160 + (i % 30) * 31, 420 + (i // 30) * 28
        d.ellipse([cx, cy, cx + 18, cy + 18], fill=REGLA)
    if t > 7.0:
        a = entra(t, 7.0, 1.0)
        escribir(d, (1160, 450), "85.769", MONO_G, SELLO, alfa=a)
        escribir(d, (1160, 595), "expedientes en", CUERPO, APUNTE, alfa=a)
        escribir(d, (1160, 645), "seis meses", CUERPO, APUNTE, alfa=a)
    if t > 10.0:
        a = entra(t, 10.0, 1.0)
        escribir(d, (1160, 750), "Un pliego: 77 páginas de PDF", SERIF_P, TINTA, alfa=a, ancho=600)


def escena_triaje(d, t, dur):
    marco(d, "Paso 1 · El filtro barato", "No abre ni un solo PDF", t)
    for i in range(474):
        cx, cy = 160 + (i % 30) * 31, 420 + (i // 30) * 28
        if t < 3.0:
            color = REGLA
        elif i % 13 == 5:
            color = SELLO
        elif i % 37 == 9:
            color = OXIDO
        else:
            k = entra(t, 3.0, 1.4)
            color = tuple(int(REGLA[j] + (FONDO[j] - REGLA[j]) * 0.82 * k) for j in range(3))
        d.ellipse([cx, cy, cx + 18, cy + 18], fill=color)

    if t > 4.6:
        a = entra(t, 4.6, 0.9)
        for i, (c, txt) in enumerate(
            [(SELLO, "pasa adelante"), (OXIDO, "duda — también pasa"), (REGLA, "descartada")]
        ):
            y = 430 + i * 62
            d.ellipse([1160, y, 1160 + 26, y + 26], fill=c)
            escribir(d, (1210, y - 8), txt, CUERPO, TINTA if c != REGLA else APUNTE, alfa=a)
    if t > 8.5:
        a = entra(t, 8.5, 0.9)
        caja(d, 1160, 640, 520, 130, alfa=a)
        escribir(d, (1195, 665), "0,04 € / 100", fuente("consolab.ttf", 56), VERDE, alfa=a)
        escribir(d, (1195, 730), "coste del filtro", CUERPO, APUNTE, alfa=a)
    if t > 12.5:
        a = entra(t, 12.5, 0.9)
        escribir(d, (1160, 820), "Nada se descarta", CUERPO_N, TINTA, alfa=a)
        escribir(d, (1160, 866), "en silencio.", CUERPO_N, TINTA, alfa=a)


def escena_pliego(d, t, dur):
    marco(d, "Paso 2 · El pliego", "77 páginas. Se leen cuatro", t)
    # 11 columnas a proposito: asi las paginas 52 a 55 caen seguidas en la misma fila y se
    # ve que se lee hacia delante desde el ancla, que es justo lo que hace el programa.
    an, al, g = 58, 52, 9
    for p in range(1, 78):
        i = p - 1
        cx, cy = 160 + (i % 11) * (an + g), 420 + (i // 11) * (al + g)
        leida = 52 <= p <= 55 and t > 6.5
        k = entra(t, 6.5, 1.2) if leida else 0
        relleno = tuple(int(PANEL[j] + (SELLO[j] - PANEL[j]) * k) for j in range(3))
        d.rounded_rectangle([cx, cy, cx + an, cy + al], radius=4, fill=relleno, outline=REGLA, width=2)
        if p == 52 and t > 4.5:
            a = entra(t, 4.5, 0.8)
            c = tuple(int(FONDO[j] + (SELLO[j] - FONDO[j]) * a) for j in range(3))
            d.rounded_rectangle([cx - 6, cy - 6, cx + an + 6, cy + al + 6], radius=6, outline=c, width=4)
    if t > 4.5:
        a = entra(t, 4.5, 0.9)
        escribir(d, (1080, 430), "ANCLA", ETIQUETA, SELLO, alfa=a)
        escribir(d, (1080, 472), "página 52", fuente("consolab.ttf", 54), TINTA, alfa=a)
        escribir(d, (1080, 540), "la que más puntúa", CUERPO, APUNTE, alfa=a, ancho=560)
    if t > 9.5:
        a = entra(t, 9.5, 1.0)
        escribir(d, (1080, 630), "5 %", MONO_M, SELLO, alfa=a)
        escribir(d, (1080, 850), "del documento que se lee", CUERPO, APUNTE, alfa=a)


CITA = "El volumen anual de negocios referido al mejor ejercicio dentro de los tres últimos disponibles será de, al menos, 93.000,00 euros."


def escena_extraccion(d, t, dur):
    marco(d, "Paso 3 · La extracción", "El modelo copia. El programa comprueba que copió", t, ancho=1560)
    a = entra(t, 2.2, 0.9)
    if a > 0:
        caja(d, 160, 430, 1600, 250, alfa=a)
        d.rectangle([160, 430, 166, 680], fill=tuple(int(FONDO[i] + (SELLO[i] - FONDO[i]) * a) for i in range(3)))
        escribir(d, (210, 465), CITA, SERIF, TINTA, alfa=a, ancho=1500)
        escribir(d, (210, 620), "pág. 52 de 77 — lo que el modelo dice que ha copiado", MONO, APUNTE, alfa=a)
    # El barrido: el programa buscando la frase en el texto de esa página.
    if 6.0 < t < 11.0:
        k = suave((t - 6.0) / 4.0)
        x = 166 + int(1594 * k)
        d.rectangle([166, 432, x, 678], fill=(28, 39, 57))
        escribir(d, (210, 465), CITA, SERIF, TINTA, ancho=1500)
        escribir(d, (210, 620), "pág. 52 de 77 — lo que el modelo dice que ha copiado", MONO, APUNTE)
        d.rectangle([x - 4, 432, x, 678], fill=SELLO)
    if t > 11.0:
        b = entra(t, 11.0, 0.8)
        caja(d, 160, 720, 640, 96, relleno=(27, 42, 33), borde=VERDE, alfa=b)
        escribir(d, (195, 745), "APARECE · verificada", fuente("consolab.ttf", 44), VERDE, alfa=b)
    if t > 14.5:
        c = entra(t, 14.5, 0.8)
        caja(d, 840, 720, 920, 96, relleno=(51, 33, 29), borde=OXIDO, alfa=c)
        escribir(d, (875, 745), "una palabra cambiada · se cae", fuente("consolab.ttf", 44), OXIDO, alfa=c)
    if t > 18.0:
        e = entra(t, 18.0, 0.9)
        escribir(d, (160, 862), "No se le pregunta si la empresa puede presentarse.", CUERPO_N, TINTA, alfa=e)


REQUISITOS = [
    ("Volumen de negocios", "pág. 52 · exige 93.000 €", "dos números", SELLO),
    ("Seguro de responsabilidad civil", "pág. 52 · 150.000 €", "a revisar", APUNTE),
    ("Trabajos similares", "pág. 52 · 113.101,50 €", "a revisar", APUNTE),
    ("Habilitación empresarial", "pág. 53", "a revisar", APUNTE),
]


def escena_decision(d, t, dur):
    marco(d, "Paso 4 · La decisión", "Decide el programa, no el modelo", t)
    for i, (que, donde, estado, color) in enumerate(REQUISITOS):
        a = entra(t, 2.0 + i * 0.9, 0.8)
        if a <= 0:
            continue
        y = 430 + i * 108
        escribir(d, (160, y), que, CUERPO_N if i == 0 else CUERPO, TINTA if i == 0 else APUNTE, alfa=a)
        escribir(d, (160, y + 50), donde, MONO, APUNTE, alfa=a)
        an = int(fuente("consolab.ttf", 34).getlength(estado)) + 50
        caja(d, 1760 - an, y + 4, an, 56, relleno=PANEL, borde=color, r=6, alfa=a)
        escribir(d, (1785 - an, y + 14), estado, fuente("consolab.ttf", 34), color, alfa=a)
        d.line([160, y + 92, 1760, y + 92], fill=REGLA, width=2)
    if t > 11.0:
        a = entra(t, 11.0, 1.0)
        escribir(
            d,
            (160, 866),
            "Solo el volumen de negocios puede descartar. El resto manda a revisar.",
            CUERPO_N,
            TINTA,
            alfa=a,
            ancho=1600,
        )


BARRAS = [("El radar", 69.2, SELLO), ("Filtro por CPV", 82.7, APUNTE), ("Filtro del perfil", 88.5, APUNTE)]


def escena_resultado(d, t, dur):
    marco(d, "Y lo que salió al medirlo", "52 contratos que ganaron de verdad", t)
    for i, (nombre, valor, color) in enumerate(BARRAS):
        a = entra(t, 2.4 + i * 1.1, 0.8)
        if a <= 0:
            continue
        y = 440 + i * 130
        escribir(d, (160, y + 18), nombre, CUERPO, APUNTE if i else TINTA, alfa=a)
        d.rounded_rectangle([620, y, 1560, y + 76], radius=6, fill=PANEL, outline=REGLA, width=2)
        k = suave(min(1.0, (t - (2.4 + i * 1.1)) / 1.8))
        an = int((1560 - 620) * (valor / 100) * k)
        if an > 8:
            d.rounded_rectangle([620, y, 620 + an, y + 76], radius=6, fill=color)
        escribir(d, (1600, y + 14), f"{valor:.1f} %".replace(".", ","), fuente("consolab.ttf", 48), TINTA, alfa=a)
    if t > 13.5:
        a = entra(t, 13.5, 0.9)
        caja(d, 160, 818, 700, 104, relleno=(51, 33, 29), borde=OXIDO, alfa=a)
        escribir(d, (200, 842), "TESIS REFUTADA", fuente("segoeuib.ttf", 56), OXIDO, alfa=a)


def escena_porque(d, t, dur):
    marco(d, "Por qué pierde", "El techo es el perfil, no el modelo", t)
    a = entra(t, 2.0, 0.9)
    if a > 0:
        caja(d, 160, 420, 760, 300, alfa=a)
        escribir(d, (200, 450), "LO QUE DICE SU PERFIL", ETIQUETA, APUNTE, alfa=a)
        escribir(d, (200, 505), "Autodesk", fuente("segoeuib.ttf", 72), TINTA, alfa=a)
        escribir(d, (200, 600), "CAD, BIM, GIS", CUERPO, APUNTE, alfa=a)
    b = entra(t, 5.0, 0.9)
    if b > 0:
        caja(d, 1000, 420, 760, 300, borde=OXIDO, alfa=b)
        escribir(d, (1040, 450), "LO QUE GANÓ DE VERDAD", ETIQUETA, OXIDO, alfa=b)
        escribir(d, (1040, 505), "Adobe · PRESTO", fuente("segoeuib.ttf", 72), OXIDO, alfa=b)
        escribir(d, (1040, 600), "10 contratos de licencias", CUERPO, APUNTE, alfa=b)
    c = entra(t, 9.0, 1.0)
    if c > 0:
        escribir(d, (160, 748), "16 de 16", MONO_G, TINTA, alfa=c)
        escribir(d, (160, 878), "contratos perdidos por un producto que el perfil no nombraba", CUERPO, APUNTE, alfa=c)


def escena_cierre(d, t, dur):
    a = entra(t, 0.3, 1.0)
    if a > 0:
        d.rectangle([160, 340, 160 + int(180 * a), 346], fill=SELLO)
        escribir(d, (160, 380), "POR QUÉ ESTO VALE ALGO", ETIQUETA, SELLO, alfa=a)
    b = entra(t, 0.9, 1.2)
    if b > 0:
        escribir(
            d,
            (160, 450 + int(20 * (1 - b))),
            "El criterio estaba escrito antes de mirar un solo dato",
            fuente("segoeuib.ttf", 84),
            TINTA,
            alfa=b,
            ancho=1600,
        )
    c = entra(t, 4.5, 1.1)
    if c > 0:
        escribir(
            d,
            (160, 740),
            "Un resultado negativo medido bien vale más que uno bueno sin medir.",
            fuente("georgiai.ttf", 60),
            SELLO,
            alfa=c,
            ancho=1600,
        )


ESCENAS = [
    escena_portada,
    escena_problema,
    escena_triaje,
    escena_pliego,
    escena_extraccion,
    escena_decision,
    escena_resultado,
    escena_porque,
    escena_cierre,
]

# El subtítulo de cada escena, partido en trozos que se van pasando al ritmo de la voz.
PIES = [
    ["Cada día se publican cientos de contratos públicos", "Y la mayoría de las empresas pequeñas no se entera", "Te voy a enseñar por qué no funcionó"],
    ["474 licitaciones nuevas cada día", "Hay que abrir el pliego: un PDF de decenas de páginas", "Nadie tiene tiempo para eso"],
    ["El filtro barato no abre ni un solo PDF", "Veinte licitaciones en cada pregunta al modelo", "La duda pasa adelante. Nada se descarta en silencio"],
    ["¿Le damos las 77 páginas a la IA? No", "Un programa sin modelo puntúa cada página", "Encuentra el ancla y lee cuatro: el 5 %"],
    ["No se le pregunta si la empresa puede presentarse", "Se le pide la frase exacta y el número de página", "Un programa la busca carácter a carácter", "Si no aparece, el requisito se cae"],
    ["No decide el modelo: decide un fichero de reglas", "Cincuenta líneas que cualquiera puede leer", "Solo el volumen descarta: es lo único que son dos números"],
    ["52 contratos que cinco empresas ganaron de verdad", "El radar encuentra el 69,2 %", "Un filtro simple por código: el 82,7 %", "La tesis queda refutada"],
    ["Pero sabemos por qué", "Los 16 contratos perdidos son productos", "que el perfil de la empresa no nombraba"],
    ["El criterio estaba escrito antes de medir", "Por eso este resultado vale algo"],
]


def pie_de(indice: int, t: float, dur: float) -> str:
    trozos = PIES[indice]
    hablado = max(0.001, dur - COLA)
    n = min(len(trozos) - 1, int(t / hablado * len(trozos)))
    return trozos[n] if t < dur - 0.15 else trozos[-1]


def duraciones() -> list[float]:
    fuera = []
    for i in range(len(ESCENAS)):
        with wave.open(str(AQUI / f"voz_{i:02d}.wav")) as w:
            fuera.append(w.getnframes() / w.getframerate() + COLA)
    return fuera


def juntar_voz(duros: list[float]) -> Path:
    """Una sola pista, con el mismo silencio de cola que se le da a cada escena."""
    destino = AQUI / "narracion.wav"
    with wave.open(str(AQUI / "voz_00.wav")) as w:
        parametros = w.getparams()
    with wave.open(str(destino), "wb") as salida:
        salida.setparams(parametros)
        for i in range(len(ESCENAS)):
            with wave.open(str(AQUI / f"voz_{i:02d}.wav")) as w:
                salida.writeframes(w.readframes(w.getnframes()))
            silencio = int(parametros.framerate * COLA) * parametros.sampwidth * parametros.nchannels
            salida.writeframes(b"\x00" * silencio)
    return destino


def main() -> None:
    duros = duraciones()
    total = sum(duros)
    voz = juntar_voz(duros)
    destino = AQUI / "radar_como_funciona.mp4"

    ff = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0",
            "-i", str(voz),
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
            str(destino),
        ],
        stdin=subprocess.PIPE,
    )

    hechos = 0
    for i, dibujar in enumerate(ESCENAS):
        cuadros = int(duros[i] * FPS)
        for n in range(cuadros):
            t = n / FPS
            img = Image.new("RGB", (W, H), FONDO)
            d = ImageDraw.Draw(img)
            dibujar(d, t, duros[i])

            # Pie fijo: la frase que se está oyendo, y la barra de avance de todo el vídeo.
            texto = pie_de(i, t, duros[i])
            lineas = partir(texto, PIE, 1500)
            alto = 40 + len(lineas) * 52
            d.rectangle([0, H - alto - 46, W, H - 46], fill=(16, 18, 21))
            y = H - alto - 24
            for linea in lineas:
                d.text((W / 2 - PIE.getlength(linea) / 2, y), linea, font=PIE, fill=TINTA)
                y += 52
            avance = (hechos + n) / max(1, int(total * FPS))
            d.rectangle([0, H - 8, int(W * avance), H], fill=SELLO)

            ff.stdin.write(img.tobytes())
        hechos += cuadros
        print(f"  escena {i + 1}/{len(ESCENAS)} · {duros[i]:.1f} s", flush=True)

    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("ffmpeg ha fallado")
    print(f"\n{destino}  ({destino.stat().st_size / 1024 / 1024:.1f} MB, {total:.0f} s)")


if __name__ == "__main__":
    main()
