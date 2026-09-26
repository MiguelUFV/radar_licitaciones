# Perfiles congelados

Un perfil es todo lo que el radar sabe de una empresa. Se escribe **antes** de medir y a
partir de fuentes públicas, sin mirar los contratos que esa empresa ganó
(`docs/REGLA_SELECCION.md` §6).

Aquí solo va la huella. El texto y las direcciones de las fuentes se quedan en
`data/privado/perfiles/`, fuera de git, porque identifican a la empresa (`docs/DATOS.md` §7).
Con la huella basta para lo que importa: comprobar que el perfil **no se ha cambiado**
después de publicar una medición.

| Empresa | Papel | Fuentes | Congelado | sha256 del perfil |
|---|---|---|---|---|
| Empresa A | desarrollo | 2 | 2026-09-26 | `11fe4ea851d94187d03d99e299fec46dc956ba322a202fb005c7e94370a72274` |

Generado por `radar/perfiles.py` el 2026-09-27.

Para comprobar uno:

```bash
sha256sum data/privado/perfiles/perfil_empresa_a.md
```
