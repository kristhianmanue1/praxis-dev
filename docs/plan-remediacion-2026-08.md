# Revisión adversarial interna y plan de remediación

**Fecha:** 2026-08-19
**Estado:** propuesta (requiere decisión humana para priorizar)
**Origen:** revisión crítica del corpus tras integrar AN-KLA beta.14 (commit
`ecd49bd`), seguida de ronda adversarial sobre los hallazgos.
**Naturaleza:** este documento es un plan de sólo lectura. No es un
`praxis/mutation-plan/v1`; las acciones que muten el árbol usan la excepción F0
de `AGENTS.md` (solicitud actual, diff y gates) hasta que F2 exista.

## Hallazgos que sobrevivieron la ronda adversarial

| # | Hallazgo | Severidad | Estado |
|---|----------|-----------|--------|
| H1 | Drift docs/realidad: `AGENTS.md` y `README.md` afirman que el CLI no existe; `praxis_dev` con `project status/audit` y `adr list/show/audit` ya está mergeado. Además `--help` falla (`unknown domain '--help'`). | media | verificado en código |
| H2 | Riesgo de ventana F0→F2: sin `plan/apply` toda mutación vive en la excepción F0; si la ventana se alarga, la excepción se vuelve el modo permanente y el estándar queda aspiracional. | alta | riesgo de duración, no de diseño |
| H3 | Gates sólo post-hoc: ningún gate actual puede rechazar una mutación no autorizada; sólo reportarla después. Toda la gobernanza vigente es cumplimiento voluntario + disciplina de Git. | alta | consecuencia declarada, no defecto oculto |
| H4 | Validación diferida: ningún piloto externo ha ejercido el contrato; `conformance/`, `adapters/` y `docs/specs/` son stubs; suite de fixtures de `docs/conformidad.md` §8 no existe. | media | verificado en árbol |
| H5 | Curva de entrada sin tooling: `minimal` sigue exigiendo asimilar huellas, clases de autoridad y doble capa de instrucciones (AGENTS.md + AN-KLA.md). El tooling que abarataría la ceremonia (`init`, errores accionables) no existe. | media | matizada; sobrevive el núcleo |
| H6 | Procedimiento de la primera promoción humana del estándar (`docs/estandar.md` §10) no documentado. | baja | menor |

Hallazgos descartados en la ronda: "limbo constitucional" (la reserva de
promoción a humano es la gobernanza correcta) y "autoridad vacía" como crítica
(el propio repo lo declara en su estado honesto).

## Plan de remediación

### P1 — Reconciliar discurso y realidad (H1) — rápida, F1

Acciones:

1. Actualizar `AGENTS.md` §Bootstrap F0: sustituir "El CLI `praxis` todavía no
   existe" por el estado real (CLI read-only parcial mergeado; mutación
   gobernada pendiente). Ajuste quirúrgico, sin tocar el bloque gestionado
   AN-KLA (edición fuera del bloque gestionado genera warning esperado).
2. Actualizar `README.md` "Estado honesto" con la misma precisión.
3. Corregir UX del CLI: soportar `--help`/-h en `praxis_dev/cli.py` con salida
   de dominios y códigos de salida contractuales; test asociado.

Cierre: `check_repo.py` PASS; tests PASS; `praxis --help` exit 0; docs sin
afirmaciones falsas verificables contra Git.

### P2 — Acortar la ventana F0→F2 (H2, H3) — prioritaria

Acciones:

1. Extraer de F2 un increment mínimo ejecutable: `project init-plan` que emita
   un `praxis/mutation-plan/v1` válido contra `schemas/plan.schema.json`
   (fingerprint RFC 8785, allowed_paths, pre/postconditions), sin apply aún.
   Esto convierte el plan de mutación de documento aspiracional en artefacto
   real ejercitable por tests.
2. Implementar `project init-apply` con: verificación de drift por
   `expected_before_sha256`, protección de paths fuera de `allowed_paths`,
   rechazo de symlinks/escape de raíz, y reporte de estado incierto sin
   escritura parcial silenciosa.
3. Migrar el flujo de trabajo interno del repo: cada mutación F0 futura
   (incluidas las de este plan) se acompaña de un mutation-plan JSON en ruta
   efímera, aunque su aplicación siga siendo revisión por diff. Dogfooding del
   contrato antes de tener enforcement.
4. Tests adversariales de cierre F2: conflicto, carrera (lock), drift,
   escape de raíz.

Cierre: existe un ciclo plan→apply real que rechaza drift; las mutaciones del
propio repo prueban el contrato; la excepción F0 queda reducida a su mínimo.

### P3 — Primera validación externa del contrato (H4)

Acciones:

1. Construir la suite de fixtures de conformidad (`docs/conformidad.md` §8):
   casos positivos y negativos por perfil, consumibles por `project audit` sin
   red ni estado global.
2. Ejecutar el piloto `minimal` en un proyecto pequeño real (roadmap F6 lo
   pide; adelantar la parte read-only no requiere F2/F4).
3. Ejecutar auditoría read-only sobre Kratos y ADRC-Python como primer
   ejercicio multi-repo del cierre F1.

Cierre: al menos un repositorio ajeno a praxis-dev pasa `project audit` y un
humano revisa el resultado.

### P4 — Abaratar la entrada (H5)

Acciones:

1. `docs/adopcion.md`: añadir una ruta de adopción de 10 minutos para
   `minimal` (checklist ejecutable, sin teoría).
2. CLI: mensajes de error accionables que citen el contrato exacto violado y
   el documento normativo relevante.
3. Documentar la relación AGENTS.md↔AN-KLA.md en un solo párrafo canónico
   (qué es cada capa, cuál manda) para reducir la superficie cognitiva de la
   doble instrucción.

Cierre: una persona ajena puede adoptar `minimal` siguiendo sólo el checklist,
sin leer `fundamentos.md` ni `modelo-autoridad.md`.

### P5 — Documentar la primera promoción humana (H6)

Acciones:

1. Redactar en `docs/estandar.md` (o ADR si cambia semántica) el procedimiento
   de la decisión humana de promoción inicial: quién, sobre qué digest, con
   qué evidencia mínima y cómo se registra.
2. Es ADR si toca semántica del estándar (requiere revisión adversarial
   independiente, regla dura 8).

Cierre: el procedimiento existe, es revisable y no autoejecutable por agente.

## Secuenciación propuesta

```
P1 (días)  ──►  P2 increment 1 (plan emit)  ──►  P2 increment 2 (apply)
                        │
                        └──►  P3 (fixtures + piloto read-only, paralelo)
P4 (paralelo a P2/P3, independiente)
P5 (corto, cualquier momento; ADR si cambia semántica)
```

Prioridad: P1 y P2-incremento-1 primero. P2 es el eje: cada semana de retraso
en F2 consolida la excepción F0 como norma de facto.

## Qué este plan no hace

- No implementa nada: cada acción requiere solicitud/autorización corriente.
- No toca autoridad F4 ni perfiles `controlled`/`sealed` (deuda declarada,
  issue #10).
- No promueve el estándar: la promoción es decisión humana externa (regla
  dura 8, `docs/estandar.md` §10).
- No modifica el bloque gestionado AN-KLA de `AGENTS.md`.
