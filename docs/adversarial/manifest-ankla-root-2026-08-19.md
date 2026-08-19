# Ronda adversarial: excepción de AN-KLA.md en raíz (regla 8, commit ecd49bd)

**Fecha:** 2026-08-19
**Objeto:** cambio al estándar en `ecd49bd`: `standards/praxis/v1/manifest.json`
(`allowed_root_markdown` += `AN-KLA.md`), regla 6 de `AGENTS.md`, `AN-KLA.md`
nuevo, `/.an-kla/` en `.gitignore`.
**Revisor:** opencode (agente) — mismo autor del cambio: auto-revisión; la
revisión adversarial independiente de la regla 8 sigue pendiente y ésta no
la sustituye.

## Hallazgos

### HM1 — La restricción "gestionado por AN-KLA" no es verificable (MEDIO)

La regla 6 permite `AN-KLA.md` "(contrato gestionado por AN-KLA)", pero el
gate sólo compara el nombre de archivo (`check_repo.py:348-351` contra
`allowed_root_markdown`). Verificado: el `AN-KLA.md` actual contiene **cero**
marcadores `an-kla:managed` (a diferencia del bloque en `AGENTS.md`, que
tiene begin/end con hash). Cualquier archivo con ese nombre pasa el gate,
gestionado o no. El paréntesis es documentación, no enforcement.

**Remediación:** aceptar riesgo residual y endurecer el wording de la regla
("el contrato raíz de AN-KLA") o exigir marcador/hash de plantilla conocida
en un futuro gate. No acoplar el gate a la herramienta externa hoy: sería
dependencia frágil entre herramientas.

### HM2 — Alternativas no documentadas al cambiar el estándar (MEDIO)

Cambiar `allowed_root_markdown` es un cambio al manifiesto versionado del
estándar (regla 8). La alternativa — reubicar `AN-KLA.md` bajo `docs/` y
preservar la regla 6 intacta — no fue evaluada ni registrada en ningún
artefacto (el commit la justifica implícitamente porque `an-kla context`
gestiona su contrato en raíz). Un cambio de estándar sin opciones
registradas viola el espíritu de ADRG §6 ("considera al menos dos opciones")
aunque esté por debajo del umbral formal de ADR.

**Remediación:** registrar la decisión con opciones en un ADR breve o una
sección de decisión en `docs/adopcion.md` §9 (que ya explica la relación).

### HM3 — Doble texto de la misma regla sin sincía (BAJO)

La lista permitida existe en dos hogares: regla 6 de `AGENTS.md` (prosa) y
`allowed_root_markdown` del manifest (machine-readable). Verificado:
coinciden exactamente hoy. Nada impide drift futuro (ningún gate
cruzado). El principio "un contenido, un hogar canónico" (regla dura 1)
designa al manifest como canónico machine-readable; la prosa de regla 6
debería declararse derivada.

### HM4 — Edición del estándar sin bump de versión (BAJO, aceptable)

El manifiesto sigue `0.1.0-draft.1` tras mutación. Aceptable mientras el
estándar esté en draft (la disciplina de §10 aplica a la promoción fuera de
draft), pero cada excepción de este tipo debe quedar registrada (ver HM2)
para que la candidata a rc no herede mutaciones silenciosas.

### HM5 — Commits de concerns mezclados (COSMÉTICO)

`ecd49bd` mezcla integración de memoria, cambio de estándar y gitignore.
Los 5 commits locales aún no publicados (`origin/main` en `1097fc2`), así
que la historia puede rehearse si el operador lo pide; no recomendado por
regla de no reescritura sin autorización explícita.

### HM6 — AN-KLA.md sin cota de tamaño (BAJO)

316 líneas hoy; `reference_repository_required_paths` fija `max_lines` para
otros archivos canónicos pero no existe entrada para `AN-KLA.md` (ni como
requerido ni acotado). Contrato externo gestionado por otra herramienta:
la ausencia de cota es razonable, pero el gate no lo declara.

## Verificación ejecutada

- `git show ecd49bd --stat`; diff exacto de regla 6 y manifest.
- `grep -c "an-kla:managed" AN-KLA.md AGENTS.md` → 0 / 2.
- `check_repo.py` (gate PASS) y lectura de `check_root_markdown` (líneas
  348-351) para confirmar comparación por nombre.
- `git log origin/main..HEAD` → 5 commits no publicados.
- Coherencia textual regla 6 ↔ manifest verificada byte a byte.

## Decisión

**proceed condicionado** — el cambio es correcto en sustancia (la
integración exige el contrato en raíz; preservar el contenido previo de
AGENTS.md; el estado local `.an-kla/` correctamente ignorado). Condiciones:
registrar opciones consideradas (HM2), declarar la prosa de regla 6 como
derivada del manifest (HM3) y aceptar explícitamente el riesgo HM1. La
ronda independiente de la regla 8 sigue pendiente para el operador humano.
