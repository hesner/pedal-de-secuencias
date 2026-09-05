# Cómo contribuir

*[Read in English](../../CONTRIBUTING.md)*

## Idioma

Todo en este repositorio —código, comentarios, mensajes de commit,
documentación— está escrito primero en inglés. Las traducciones al
español viven en `docs/es/` junto al original en inglés; si cambias un
archivo `.md` de la raíz que tiene contraparte en español, por favor
actualiza ambos (o dilo en tu PR si no puedes, y alguien le dará
seguimiento).

## Antes de abrir un PR

```
python3 -m unittest discover -s tests -v
```

Todos los tests deben pasar; ninguno necesita hardware. El CI corre este
mismo comando automáticamente en cada push y pull request.

## Agregar soporte para un controlador MIDI distinto

Esta es la razón más probable para contribuir. La arquitectura existe
específicamente para que esto sea un cambio contenido:

```
CONTROLADOR MIDI  →  Adapter  →  Mapper  →  Core
```

- Tu trabajo va en un módulo nuevo dentro de `src/adapter/`, siguiendo la
  forma de `src/adapter/mvave_adapter.py`.
- El `Mapper` (`src/mapper/`) y el `Core` (`src/core/`) no deberían
  necesitar ningún cambio — solo ven Program Change MIDI estándar y
  acciones abstractas (`SelectTrack`, `Stop`), nunca nada específico de
  un controlador en particular. Si necesitas tocar alguno de los dos para
  soportar un controlador nuevo, probablemente algo de ese controlador
  debería estar en el Adapter en su lugar — abre un issue para discutirlo
  primero.
- Documenta contra qué lo probaste (dispositivo, firmware/modo, y cómo
  confirmaste el mapeo), de la misma forma que `MAVAVE_ANALYSIS.md` lo
  hace para el M-VAVE PD41.

## Razonamiento de diseño y decisiones previas

`MASTER_SPECIFICATION.md` es el contrato real de este proyecto — cada
decisión de arquitectura aprobada y por qué se tomó. `TESTING.md` tiene
el historial de validación en hardware real. Lee ambos antes de proponer
un cambio a un comportamiento existente; es probable que la alternativa
ya se haya probado y descartado por una razón documentada (ej. hot-swap
del USB en plena sesión, o forzar la tasa de refresco nativa de la
pantalla).

## Estilo de código

Sigue lo que ya existe: módulos pequeños de un solo propósito,
dataclasses para datos simples (ver `src/mapper/actions.py`), sin
dependencias de Python de terceros (solo librería estándar), comentarios
que expliquen el *por qué* en vez de repetir lo que ya dice el código.
