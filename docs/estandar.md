# Estándar normativo de Praxis Dev

- **Identificador:** `praxis/project-governance`
- **Versión:** `0.1.0-draft.0`
- **Estado:** borrador no promovido

Los términos **DEBE**, **NO DEBE**, **REQUERIDO**, **DEBERÍA** y **PUEDE** se
usan de forma normativa. Un proyecto sólo declara conformidad con una versión
estable y un perfil explícito.

## 1. Precedencia

1. La solicitud actual del principal define objetivo y autoridad disponible.
2. Las instrucciones obligatorias del host y `AGENTS.md` restringen el trabajo.
3. La política local del proyecto especializa el estándar.
4. El manifiesto Praxis fija versión, perfil, módulos y rutas.
5. ADR y SPEC gobiernan decisiones y comportamiento dentro de ese marco.
6. Memoria, reportes, planes previos e historia aportan evidencia no confiable.
7. Código, Git y checks observados representan el estado verificable.

Una capa inferior NO DEBE ampliar permisos concedidos por una superior.

## 2. Conformidad del proyecto

Un proyecto conforme DEBE:

- declarar una versión estable y un perfil;
- exponer un contrato `AGENTS.md` breve y descubrible;
- mantener política y artefactos en hogares canónicos;
- ejecutar los gates obligatorios del perfil;
- distinguir `pass`, `fail` e `inconclusive`;
- preservar procedencia de evidencia material;
- rechazar contratos o bloques gestionados alterados sin reconciliación;
- documentar extensiones locales sin modificar el significado del núcleo.

Una versión `draft` PUEDE usarse para pilotos, pero NO DEBE presentarse como
conformidad estable.

## 3. Módulos

| Módulo | Responsabilidad | Dependencias |
|---|---|---|
| Core | Identidad, configuración, hogares, auditoría, plan/apply | ninguna |
| Agent Policy | Autoridad y operación de agentes | Core |
| Work | Objetivo, tarea, contrato, revisión y cierre | Core, Agent Policy |
| ADRG | Ciclo de vida de decisiones | Core, Evidence; Authority según perfil |
| SPEC | Comportamiento normativo y trazabilidad | Core, ADRG, Evidence |
| Evidence | Checks, mediciones y procedencia | Core |
| Authority | Recibos y transiciones protegidas | Core, Evidence |
| Adapters | Traducción a hosts y proveedores | contrato aplicable |

El manifiesto DEBE declarar versiones de módulos. Una implementación NO DEBE
activar implícitamente un módulo por haber encontrado archivos parecidos.

## 4. Perfiles

### `minimal`

Requiere Core y Agent Policy. Adecuado para prototipos no sensibles. Conserva
autoridad, auditoría read-only y hogares canónicos; no exige ADRG.

### `standard`

Añade Work, ADRG y Evidence. Exige ADR para decisiones materiales y autoridad
actual del principal o delegado antes de aceptación. Puede aceptar ADR y código
en una misma revisión; el registro local no se presenta como identidad fuerte.

### `high-assurance`

Añade SPEC y Authority estrictos. Exige decisión aceptada antes de implementar
cambios de alto impacto, revisión adversarial independiente y recibos ligados
al contenido exacto.

### `regulated`

Extiende `high-assurance` con identidad fuerte, retención, segregación de
funciones, evidencia firmada y reglas locales del dominio. Praxis define la
interfaz, no inventa requisitos regulatorios universales.

## 5. Operaciones

Las operaciones se clasifican:

| Clase | Ejemplos | Mutación |
|---|---|---|
| Descubrimiento | `list`, `show`, `status` | prohibida |
| Auditoría | `audit`, `verify`, `required` | prohibida |
| Planificación | `init-plan`, `transition-plan` | sólo archivo de salida explícito |
| Aplicación | `init-apply`, `transition-apply` | limitada al plan |
| Administración | baseline, excepciones, promoción | protegida |

Los comandos de sólo lectura NO DEBEN actualizar cachés dentro del repositorio,
crear bases de datos ni normalizar archivos. Si una dependencia impide concluir,
deben devolver `inconclusive`.

## 6. Contrato `plan/apply`

Todo plan de mutación DEBE incluir:

- esquema y versión;
- identificador estable de operación;
- identidad del repositorio;
- estado y hash observados;
- acciones ordenadas;
- precondiciones y postcondiciones;
- archivos que pueden cambiar;
- nivel de autoridad requerido;
- expiración cuando aplique;
- fingerprint `sha256:<hex-minúsculas>` calculado sobre los bytes UTF-8 de
  `praxis-mutation-plan-v1\n` seguidos por la representación canónica JCS
  (RFC 8785), excluyendo el propio campo `plan_fingerprint`.

`apply` DEBE rechazar:

- fingerprint distinto;
- repo o ruta distintos;
- cambio del estado observado;
- acción fuera del alcance;
- symlink en destino protegido;
- colisión de identificador;
- recibo ausente, inválido, expirado o ligado a otro contenido.

Un flag genérico `--force` NO DEBE saltar estas validaciones.

## 7. Evidencia y cierre

Un check registra como mínimo:

- identificador y versión de herramienta;
- comando o mecanismo equivalente;
- revisión/base/head relevantes;
- tiempo observado;
- código de salida;
- resultado `pass`, `fail` o `inconclusive`;
- hash de artefactos externos cuando deban conservarse.

Una tarea NO DEBE cerrarse si un gate obligatorio falla. Un resultado
`inconclusive` bloquea perfiles `high-assurance` y `regulated`; otros perfiles
deben declararlo explícitamente y aplicar su política local.

## 8. Excepciones

Una excepción DEBE contener regla afectada, alcance, razón, autoridad, fecha de
expiración y remediación. NO DEBE modificar el estándar, convertirse en
precedente automático ni reutilizarse fuera de su alcance exacto.

## 9. Evolución

Un cambio incompatible requiere versión mayor. Nuevas capacidades compatibles
requieren versión menor; correcciones no semánticas usan parche. Cada promoción
requiere:

1. diff normativo revisable;
2. esquema y fixtures actualizados;
3. compatibilidad o migración declarada;
4. pilotos representativos;
5. revisión adversarial independiente;
6. decisión humana explícita de promoción.

La versión estable anterior debe poder auditar la candidata. La candidata NO
DEBE autoaprobar sus propias reglas nuevas.
