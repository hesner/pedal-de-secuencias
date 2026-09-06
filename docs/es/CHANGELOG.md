# Registro de cambios

*[Read in English](../../CHANGELOG.md)*

El formato sigue libremente [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Este proyecto todavía no usa números de versión — es un aparato dedicado
único, no una librería versionada — así que las entradas se agrupan por
fecha hasta que eso cambie.

## [Sin publicar]

- Se agregó `LIBRARY.md` (en/es): cómo nombrar carpetas/archivos del USB
  de biblioteca, y el error exacto de espaciado en el nombre de archivo
  (`A  - x.mov` vs `A - x.mov`) que falla completamente en silencio —
  encontrado en vivo probando un video del Set 5 que no se reproducía.
- Proyecto renombrado de "Sequence Pedal" / "Pedal de Secuencias" a
  **Chocolate Pi** -- un nombre de producto propio (juego de palabras
  con el pedal M-VAVE Chocolate + la Raspberry Pi que realmente se usan)
  en vez de una descripción literal. Repo, badges y documentación
  actualizados; GitHub redirige automáticamente la URL vieja del repo.

## 2026-09-05 -- Primera publicación open source

Primer release open source. En uso activo y validado contra hardware
real (Raspberry Pi 2, interfaz de audio USB Behringer U-PHORIA UM2,
controlador MIDI M-VAVE PD41, USB de biblioteca).

- Arquitectura por capas (Adapter → Mapper → Core) para que el código
  específico de un controlador nunca se filtre a la lógica de
  reproducción.
- `Adapter` validado contra un M-VAVE PD41 en modo Program Change A (ver
  `MAVAVE_ANALYSIS.md` para el mapeo empírico y su corrección: 8 grupos,
  no 32).
- `Core`: resolución de biblioteca desde un USB, video manejado por
  `mpv` con loop de standby, un carril de audio dedicado para pistas de
  solo audio, y audio siempre priorizado sobre video.
- Video de standby de respaldo local para cuando el USB de biblioteca no
  está presente al arrancar.
- Servicio de `systemd` para arranque automático; la presencia del USB
  se revisa una sola vez al arrancar (sin hot-swap en vivo — hace falta
  reiniciar para tomar cambios de biblioteca).
- Sistema de archivos raíz de solo lectura (overlay de Raspberry Pi OS)
  para poder apagar la Pi en cualquier momento sin riesgo de corrupción
  del sistema de archivos.
- Licencia MIT, documentación bilingüe (inglés primero, español en
  `docs/es/`), GitHub Sponsors.
