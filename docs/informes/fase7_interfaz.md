# Fase 7 — Correo y ficha

Estado al 28-09-2026: **el correo funciona y la fase sigue abierta**, porque su puerta de salida es
«correo real recibido durante 5 días laborables seguidos» y eso solo lo cierra el calendario. El
primer correo real salió el 28-09-2026.

Lo que sí está hecho y se puede ver hoy:

```bash
uv run python -m radar.ficha --licitacion 65034 --empresa "Empresa A"
uv run python -m radar.correo --empresa "Empresa A"
```

## 1. La ficha

Es lo único del radar que ve una persona que no programa, y tiene un trabajo concreto: que alguien
con veinte minutos decida si se presenta **y pueda desconfiar del radar**. Si la ficha no se puede
comprobar contra el PDF, no vale nada.

De ahí salen las tres decisiones de diseño, que no son decoración:

- **Dos voces, dos tipografías.** La cita del pliego va en serif y lo que concluye el radar en sans.
  Sin leer nada se distingue lo que pone el documento oficial de lo que ha deducido una máquina.
- **La página, a la izquierda de una regla vertical.** Todo lo que está a la derecha de la regla sale
  de esa página. Es la coordenada para abrir el PDF y mirarlo.
- **El color marca la comprobación, no la decisión.** El número de página va en azul de sello cuando
  la cita se verificó letra a letra, y en óxido cuando no se pudo. La decisión (puede presentarse /
  no puede / hay que revisarlo) es una frase, no un semáforo: «revisar» es el caso más común del
  radar, y un ámbar convertiría lo normal en una alarma.

Lo que **no** lleva: el NIF de la empresa, nombres de personas, ni una sola palabra de jerga interna.
Hay un test por cada una de esas tres cosas.

## 2. El correo del día

Lo primero del correo no es un saludo ni un resumen: es la lista de licitaciones, una por línea, con
lo que el radar ha decidido y por qué. Lo que ha costado el día y cuántas se han mirado va al pie,
que es donde va lo que solo se consulta cuando se duda.

Va en HTML y en texto, con tabla y estilos en línea, **sin tipografías externas, sin imágenes y sin
JavaScript**: un cliente de correo bloquea o recorta todo eso, y si el correo depende de ello llega
roto. También hay un test de eso.

Un día sin nada también manda correo y lo dice. Un silencio no se distingue de una avería.

## 3. Quién envía, y por qué no es el agente

El agente **compone** el correo y lo sirve en `GET /correo/hoy`; **n8n lo envía** con su credencial
SMTP. Es la decisión D25 y el motivo sigue siendo el mismo: si lo que falla es el agente, un aviso que
pasara por el agente no llegaría nunca.

Los dos workflows llevan ya su nodo de correo, definidos en código y exportados a `n8n/workflows/`:

| Workflow | Qué manda | Cuándo |
|---|---|---|
| `radar_diario` | El correo del día, pedido a `/correo/hoy` | Después de la ingesta y de bajar los pliegos |
| `radar_errores` | El aviso de fallo, con el texto que ya se guardó en `incidencias` | Cuando cualquier workflow del radar se cae |

En `radar_errores` el orden importa y hay un test que lo fija: **primero se anota en la base y después
se avisa.** Si el correo falla, la incidencia queda escrita igual.

Ninguna contraseña viaja en esos ficheros: la credencial se referencia por su nombre (`SMTP del
radar`) y la contraseña vive cifrada dentro de n8n. Hay un test que recorre las definiciones buscando
cualquier cosa que parezca una contraseña.

## 4. Comprobado de extremo a extremo el 28-09-2026

La credencial SMTP existe en n8n (`SMTP del radar`) y el correo **ha salido de verdad**: se disparó
`radar_prueba_correo` y la ejecución terminó en `success`. Asunto recibido: «Radar de licitaciones ·
28-09: nada nuevo», que es el caso de un día sin pliegos leídos.

Dos cosas que aparecieron al probarlo:

1. **El primer intento falló con un 404.** El contenedor del agente llevaba el código de antes de que
   existiera `/correo/hoy`: n8n hablaba con una versión vieja. Es la segunda vez que pasa, así que
   ahora está en `docs/ENTORNO.md` §10 con su comando (`docker compose up -d --build agente`).
2. **El webhook de prueba se ha desactivado** después de comprobarlo. Un webhook que manda correos y
   que nadie vigila no tiene por qué quedarse encendido; para volver a probar, se activa, se lanza y
   se apaga.

La cuenta usada es la personal, con contraseña de aplicación, y por qué está en la decisión D37.

## 5. Lo que falta, y es tuyo

Solo queda una cosa, y es tiempo: **cinco días laborables seguidos** con el ordenador encendido a
las 07:00 y el correo llegando. Eso cierra la fase.

Mientras tanto, el correo de cualquier día se puede leer sin enviarlo:
`uv run python -m radar.correo --empresa "Empresa A"`.

## 6. Lo que queda fuera de esta fase

- **Los botones «me presento / no me presento»** (opcional en el ROADMAP). No están. Necesitan un
  webhook de n8n y una tabla `feedback_usuario`, y con el resultado de la Fase 5 —la tesis refutada—
  hay cosas más útiles que hacer antes.
- **Una ficha por empresa y por día en un solo sitio.** Hoy la ficha se genera de una en una a un
  fichero. El correo enlaza al expediente en la Plataforma, no a la ficha, porque la ficha todavía no
  se publica en ningún sitio al que se pueda enlazar.
