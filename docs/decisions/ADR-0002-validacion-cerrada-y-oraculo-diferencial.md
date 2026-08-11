<!-- praxis:adr
{
  "schema": "praxis/adr-metadata/v1",
  "id": "ADR-0002",
  "title": "Validación cerrada en runtime y oráculo diferencial en CI",
  "status": "proposed",
  "created_at": "2026-08-11T18:38:57Z",
  "origin": "agent_assisted",
  "authors": ["Codex"],
  "decision_owners": ["Kris Nova"],
  "assurance_profile": "standard",
  "supersedes": [],
  "superseded_by": null,
  "related": ["ADR-0001"],
  "decision_core_sha256": null,
  "transitions": [
    {
      "from": null,
      "to": "draft",
      "at": "2026-08-11T18:38:57Z",
      "authority_receipt": null,
      "authority_receipt_sha256": null
    },
    {
      "from": "draft",
      "to": "proposed",
      "at": "2026-08-11T18:38:57Z",
      "authority_receipt": null,
      "authority_receipt_sha256": null
    }
  ]
}
-->

# ADR-0002: Validación cerrada en runtime y oráculo diferencial en CI

## Contexto y problema

El CLI de Praxis requiere validar los contratos JSON versionados sin introducir
dependencias externas en el zipapp inicial. La evaluación diferencial aislada
contra `jsonschema==4.26.0` mostró que los esquemas actuales usan un subconjunto
conocido de Draft 2020-12, pero también identificó políticas propias de Praxis:
timestamps UTC estrictos y rechazo de claves JSON duplicadas antes de validar.

Usar una implementación general en runtime no elimina esas políticas y añade
dependencias, incluidas extensiones nativas, al artefacto portable. Mantener
validadores distintos por contrato duplicaría la semántica de los esquemas.

## Alcance y no objetivos

Esta propuesta define la frontera de validación del runtime y de CI para el
subconjunto actual de esquemas Praxis. No declara conformidad general con Draft
2020-12, no acepta esta decisión, no publica un artefacto y no sustituye las
validaciones de autoridad, procedencia o firma.

## Drivers e invariantes

- El zipapp inicial conserva cero dependencias externas en runtime.
- Los esquemas empaquetados permanecen como fuente canónica de forma.
- El runtime falla cerrado ante keywords o formatos no soportados.
- La política UTC y la detección de claves duplicadas se aplican en fronteras
  explícitas y separadas del esquema.
- El comportamiento del subconjunto se compara en CI contra una implementación
  de referencia fijada, sin convertirla en autoridad canónica.

## Opciones consideradas

### A. Validador cerrado con biblioteca estándar y oráculo diferencial en CI

El runtime implementa sólo el subconjunto usado por los esquemas empaquetados.
CI meta-valida los esquemas, verifica su inventario de keywords y ejecuta una
matriz diferencial contra una versión fijada de `jsonschema`.

### B. `jsonschema` en runtime

Entrega semántica general, pero añade una cadena de dependencias y `rpds-py`,
una extensión nativa. Aun requeriría código Praxis para UTC estricto y claves
duplicadas, y debilita el objetivo de un zipapp único portable.

### C. Validadores manuales por contrato

Evita dependencias, pero cada contrato se convierte en una segunda fuente de
semántica y aumenta el riesgo de deriva frente a los esquemas.

## Decisión

Proponer la opción A: un validador cerrado y sin dependencias en runtime, usado
sólo con esquemas empaquetados que hayan pasado metavalidación e inventario de
subconjunto en CI. `jsonschema==4.26.0` se usa en CI como implementación de
referencia para pruebas diferenciales, no como fuente de autoridad.

El validador no aceptará esquemas arbitrarios. Keywords o formatos fuera del
subconjunto producirán fallo cerrado. El parseo JSON rechazará claves duplicadas
y la política `date-time` de Praxis exigirá UTC expresado con `Z` o `+00:00`.

## Consecuencias

### Positivas

- Mantiene el artefacto inicial portable y sin dependencias externas.
- Hace visible cada diferencia de política y cada ampliación de esquema.
- Conserva una red diferencial independiente contra regresiones semánticas.

### Negativas

- El subconjunto debe mantenerse y probarse explícitamente.
- CI requiere un entorno de oráculo fijado y verificable.
- No se puede presentar el runtime como validador completo de Draft 2020-12.

### Neutrales

- `jsonschema` sigue siendo una dependencia de CI, no de distribución.
- Los esquemas continúan validando forma, no autoridad ni procedencia.

## Seguridad, migración y reversibilidad

Antes de uso productivo se debe corregir la semántica de `integer` o retirar
ese keyword del subconjunto soportado. Cualquier schema nuevo se meta-valida y
se rechaza si introduce un keyword no soportado. La decisión es reversible:
una futura necesidad de semántica general puede motivar un ADR nuevo que cambie
la distribución y la matriz de plataformas.

## Confirmación

La propuesta se confirmará cuando:

1. fixtures cubran los siete esquemas y los keywords pendientes;
2. las pruebas diferenciales separen coincidencias, políticas y defectos;
3. el entorno de oráculo tenga locking verificable con hashes;
4. el zipapp se construya y se ejecute sin `jsonschema` instalado;
5. los gates del repositorio y una revisión adversarial independiente pasen.

## Relaciones con ADR, SPEC e implementación

Esta propuesta concreta el runtime CLI previsto por ADR-0001. La primera
implementación debe limitarse a la validación cerrada, sus fixtures y los gates
de CI; no debe activar transiciones protegidas ni aceptar ADR por sí misma.

## Disparadores de revisión

- Un schema requiere un keyword fuera del subconjunto.
- La matriz diferencial encuentra una divergencia no documentada.
- Una dependencia runtime resulta necesaria para portabilidad o seguridad.
- El zipapp deja de poder distribuirse sin extensiones nativas.

## Referencias y evidencia

- `docs/contrato-cli.md` §§2, 3 y 9.
- `docs/distribucion-homebrew.md` §§3 y 6.
- Evaluación temporal reproducible en
  `/private/tmp/praxis-f1-jsonschema-oracle/architecture_assessment.md`.
