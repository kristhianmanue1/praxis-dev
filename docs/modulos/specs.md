# SPEC Governance y relación ADR–SPEC

## 1. Separación

| Artefacto | Pregunta principal |
|---|---|
| ADR | ¿Por qué elegimos esta dirección? |
| SPEC | ¿Qué comportamiento debe cumplir? |
| Plan/tarea | ¿Cómo organizamos la implementación? |
| Evidencia | ¿Qué observamos al verificar? |
| Reporte | ¿Qué ocurrió durante una ejecución? |

Combinar estos estados vuelve mutable el historial de decisión y convierte la
documentación en una narración difícil de verificar.

## 2. Contrato SPEC

Una SPEC promovida incluye:

- identificador, título, versión y estado;
- ADR gobernantes o `adr: none` con razón;
- alcance y archivos/componentes cubiertos;
- interfaces, tipos, esquemas e invariantes;
- comportamiento observable y errores;
- compatibilidad y migración;
- criterios de aceptación;
- checks y fixtures;
- límites conocidos;
- revisión desde commit o versión exactos.

`none` no puede mezclarse con identificadores ADR. En una SPEC aprobada,
`covers` no puede estar vacío y `valid_from` fija una revisión inmutable como
`{kind: git_commit, value: <hash completo>}` o una release SemVer como
`{kind: release, value: <versión>}` desde la que el contrato fue comprobado.
No se aceptan ramas ni tags mutables como revisión.

## 3. Cardinalidad

- Un ADR puede gobernar varias SPEC.
- Una SPEC puede estar condicionada por varios ADR compatibles.
- La relación se declara en la SPEC y se deriva en índices.
- El ADR puede enlazar SPEC por comodidad, pero el gate evita dos listas
  manuales divergentes.

## 4. Estados

Los estados SPEC se definirán en su esquema propio y no deben reutilizar estados
ADR para significados distintos. Como mínimo: `draft`, `review`, `approved`,
`deprecated`, `superseded`. Implementación y cobertura se derivan por separado.

## 5. Spec-first proporcional

El perfil `high-assurance` exige SPEC antes de modificar contratos públicos,
persistencia o autoridad. `standard` permite SPEC y código en la misma revisión
si los checks prueban coherencia. Correcciones internas pueden quedar cubiertas
por SPEC existente.

## 6. Drift y cobertura

El gate debe detectar:

- archivo cubierto cambiado después de la revisión declarada;
- componente material sin SPEC cuando el perfil la exige;
- referencia a ADR inexistente o no aceptado;
- SPEC aprobada con placeholders;
- schema/API observada distinta del contrato;
- baseline de cobertura que decrece sin excepción.

La cobertura porcentual es señal, no corrección: una SPEC superficial no debe
contar igual que un contrato verificable.

## 7. Evidencia de implementación

`accepted ADR + approved SPEC` no significa código implementado. La condición
de implementación se deriva de archivos, tests y evidencia asociados a una
revisión. El dashboard puede proyectarla; no se reescribe el ADR para narrarla.
