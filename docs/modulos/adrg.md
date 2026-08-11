# ADRG — gobernanza de decisiones arquitectónicas

## 1. Propósito

ADRG administra Architecture Decision Records creados o asistidos por agentes.
Un ADR captura una decisión arquitectónicamente significativa, su contexto,
alternativas y consecuencias. No es un plan, reporte, SPEC, incidente ni
registro de progreso.

## 2. Cuándo se requiere ADR

`praxis adr required` devuelve tres estados:

- `required`: una regla explícita exige decisión;
- `not_required`: una exención explícita aplica;
- `indeterminate`: falta intención o evidencia suficiente.

Disparadores iniciales:

- API, CLI, esquema o contrato público;
- formato persistente, migración o compatibilidad;
- autenticación, autorización, secretos, privacidad o seguridad;
- concurrencia, durabilidad, consistencia o recuperación;
- dependencia estratégica o lock-in de proveedor;
- arquitectura entre componentes o repositorios;
- política de agentes, gobernanza, autoridad o memoria;
- cambio costoso de revertir o con múltiples alternativas razonables.

Exenciones iniciales:

- corrección que restaura comportamiento ya aceptado;
- refactor interno sin cambio de contrato;
- texto editorial sin cambio normativo;
- experimento aislado, no productivo y explícitamente desechable;
- actualización rutinaria cubierta por decisión vigente.

Una clasificación de IA puede recomendar; reglas de paths, diff e intención
proporcionan la decisión mecánica. `indeterminate` falla cerrado en perfiles
altos.

## 3. Identidad y archivo

Formato inicial:

```text
docs/decisions/ADR-0001-slug.md
```

- El número es único, monotónico y nunca reutilizado.
- Los huecos son válidos.
- El slug es descriptivo y no forma parte de la identidad.
- El índice se genera desde metadatos; no es otra fuente de estado.
- Colisiones entre ramas fallan al actualizar la base o fusionar.

## 4. Estados

```text
draft ─────► proposed ─────► accepted
  │              ├────────► rejected
  └──────────────┴────────► withdrawn
accepted ─────────────────► superseded
accepted ─────────────────► retired
```

- `draft`: trabajo editable sin solicitud formal de decisión.
- `proposed`: candidato completo listo para revisión.
- `accepted`: decisión autorizada sobre contenido exacto.
- `rejected`: alternativa considerada y no adoptada.
- `withdrawn`: autor retira la propuesta antes de decisión.
- `superseded`: otra decisión aceptada la reemplaza.
- `retired`: el contexto terminó sin reemplazo.

`implemented`, `open`, `solved` y `complete` no son estados de decisión.

## 5. Transiciones

Permitidas:

```text
draft -> proposed | withdrawn
proposed -> accepted | rejected | withdrawn
accepted -> superseded | retired
```

No se permiten transiciones inversas. Un cambio de criterio crea otro ADR. El
reemplazo debe crear/aceptar el nuevo ADR y actualizar las relaciones de ambos
en una sola operación lógica. Si la plataforma no puede completar todas las
escrituras, reporta resultado incierto y exige auditoría.

## 6. Contenido obligatorio

1. Contexto y problema.
2. Alcance y no objetivos.
3. Drivers e invariantes.
4. Opciones consideradas.
5. Decisión.
6. Consecuencias positivas, negativas y neutrales.
7. Seguridad, privacidad, migración y reversibilidad cuando apliquen.
8. Confirmación mediante checks observables.
9. Relaciones con ADR, SPEC e implementación.
10. Disparadores de revisión.
11. Referencias y evidencia.

Un ADR de alto impacto considera al menos dos opciones, o demuestra por qué
sólo una es viable. Frases genéricas como “mejor”, “robusto” o “seguro” deben
traducirse a drivers o checks.

## 7. Metadatos

El esquema inicial incluye:

- `schema`, `id`, `title`, `status`;
- `created_at` y `transitions` append-only;
- `origin`: `human`, `agent_assisted`, `agent_generated`;
- `authors` y `decision_owners` como procedencia declarada;
- `assurance_profile`;
- `supersedes`, `superseded_by`, `related`;
- `decision_core_sha256` después de aceptación;
- referencia y digest de autoridad dentro de cada transición, cuando apliquen.

Las relaciones con SPEC se declaran canónicamente en `governed_by` de cada
SPEC y se proyectan hacia el ADR; no se mantiene otra lista manual.

Los nombres declarados no prueban identidad. La autoridad se verifica fuera del
documento.

`status` y `created_at` son proyecciones verificadas del historial: el primero
coincide con el último `to` y el segundo con el `at` de creación. Los tiempos de
propuesta, decisión y reemplazo se derivan de `transitions`; no se mantienen en
campos paralelos.

## 8. Inmutabilidad

Al aceptar, se calcula un digest sobre el núcleo semántico: título, contexto,
alcance, drivers, opciones, decisión y consecuencias. El algoritmo v1
normaliza CRLF a LF y concatena bytes UTF-8 así:

```text
praxis-decision-core-v1\n
title:<title>\n
## <section-1>\n<body-1>...## <section-6>\n<body-6>\n
```

Las secciones siguen exactamente el orden de §6 desde `Contexto y problema`
hasta `Consecuencias`; sólo se eliminan saltos LF al inicio y final de cada
cuerpo. El valor almacenado es `sha256:<hex-minúsculas>`. Por diseño, cambios
de espacios dentro del título o cuerpos invalidan el digest: el verificador no
intenta adivinar equivalencia semántica. Ese núcleo no se edita. Estado y
relaciones sólo cambian por transición gobernada. Correcciones editoriales que
afecten interpretación requieren addendum o reemplazo.

## 9. IA y revisión

Los agentes pueden redactar y comparar opciones, recuperar decisiones
relacionadas, verificar estructura y buscar contradicciones. No pueden:

- aceptar su propia propuesta;
- elevar consenso de modelos a autoridad;
- inventar opciones para cumplir una cuota;
- ocultar consecuencias negativas;
- convertir ausencia de evidencia en confirmación;
- cambiar el núcleo después de recibir aprobación.

Toda contribución declara origen. La revisión adversarial debe comprobar
drivers omitidos, reversibilidad, seguridad, costos y compatibilidad.

## 10. Gates

- esquema, nombre e identificador canónicos;
- estados y fechas válidos;
- secciones presentes y sin placeholders;
- relaciones existentes y recíprocas;
- ausencia de reportes en el directorio ADR;
- digest del núcleo aceptado sin drift;
- recibo ligado al plan y contenido;
- reemplazo atómico;
- SPEC relacionadas existentes;
- índice generado actualizado;
- cambio sensible acompañado por ADR aceptado según perfil.

## 11. Legado

La adopción no renumera ADR históricos automáticamente. Un inventario clasifica
duplicados, estados desconocidos, documentos mal ubicados y enlaces rotos. El
baseline tolera sólo defectos identificados y bloquea crecimiento. Los ADR
nuevos cumplen el contrato estricto desde el primer día.
