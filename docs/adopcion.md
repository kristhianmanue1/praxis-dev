# Adopción y migración

## 1. Principio

Adoptar Praxis no significa reemplazar la organización de un proyecto por una
plantilla genérica. Significa declarar un contrato, identificar conflictos y
aplicar únicamente assets compatibles mediante un plan revisado.

## 1bis. Ruta rápida `minimal` (10 minutos)

Para un proyecto pequeño que sólo quiere el contrato básico, sin leer el
corpus normativo completo:

1. Desde la raíz del repo consumidor, con este repositorio disponible:
   ```bash
   python3.12 -m praxis_dev project init-plan <repo> --output /tmp/plan.json
   ```
   Revisa el JSON: cinco archivos (`create`), un `plan_fingerprint`.
2. Un humano revisa el plan y conserva su `plan_fingerprint` (es el compromiso
   que vas a aplicar, byte exacto).
3. Aplica exactamente ese fingerprint:
   ```bash
   python3.12 -m praxis_dev project init-apply <repo> --plan /tmp/plan.json \
     --expected-fingerprint sha256:<el-que-revisaste>
   ```
4. Edita `AGENTS.md` y `POLICY.md` (son stubs tuyos, no de Praxis).
5. Copia `schemas/project-config.schema.json` desde el estándar a tu repo (el
   audit valida la configuración contra el schema local; sin él reporta
   `inconclusive`, nunca `pass`).
6. Verifica: `python3.12 -m praxis_dev project audit <repo>` debe terminar
   `pass` (exit 0).

Si algo cambió entre 1 y 3 (otra persona, otro agente, tú mismo), `init-apply`
aborta con exit 5 y te obliga a replanificar. Eso es todo: no hay paso 7.

Evidencia ejecutada (2026-08-19): ciclo completo plan→apply→audit sobre un
repositorio git vivo terminó `pass (minimal, L1)` con fingerprint revisado
`sha256:562fc574…`; re-apply del mismo plan abortó exit 5 (drift), como debe.

## 2. Proyecto nuevo

Flujo previsto:

```bash
praxis project init-plan <repo> --profile standard --output <plan>
praxis project init-apply <repo> --plan <plan> \
  --expected-fingerprint <sha256:...>
praxis project audit <repo>
```

El plan clasifica cada destino:

- `create`: no existe y puede crearse;
- `identical`: coincide con el asset esperado;
- `managed-update`: bloque conocido con actualización disponible;
- `conflict`: existe contenido no reconciliable automáticamente;
- `skip`: no aplica al perfil.

La aplicación se bloquea si existe `conflict`.

## 3. Proyecto existente

La adopción comienza read-only:

1. inventariar contratos, políticas, ADR, SPEC, memoria y gates;
2. detectar hogares duplicados y referencias rotas;
3. clasificar reglas locales que deben preservarse;
4. escoger perfil inicial realista;
5. crear baseline explícito para deuda histórica;
6. generar un plan de estructura sin sobrescrituras;
7. revisar y aplicar;
8. activar gates sólo para deuda nueva;
9. reducir baseline por iteraciones separadas.

No se renumeran decisiones ni se mueve documentación masivamente durante el
bootstrap salvo autorización específica. Migración y saneamiento son hitos
distintos.

## 4. Estrategia de bloques gestionados

Los archivos always-on necesitan contenido local disponible incluso si el CLI
no está instalado. Praxis puede gestionar un bloque delimitado con:

```text
schema + standard_version + template_id + content_sha256
```

El proyecto mantiene extensiones fuera del bloque. `upgrade-plan` compara:

- template instalado;
- template objetivo;
- bloque observado;
- contenido local fuera del bloque.

Un bloque modificado manualmente falla cerrado. El contenido externo se
preserva y sólo se incorpora a una nueva baseline mediante confirmación
explícita.

## 5. Configuración

`.praxis.toml` contiene únicamente configuración estable:

- `project_id` inmutable, versión, perfil y ciclo operativo;
- módulos activos;
- rutas canónicas;
- proveedor y conducta de enforcement de autoridad;
- extensiones locales.

La versión inicial crea proyectos con `lifecycle=development` y
`authority.enforcement=advisory`. La ausencia del adaptador produce una
degradación visible, no una aprobación implícita. Una futura promoción de ciclo
será una migración gobernada, no una edición ordinaria de TOML.

No guarda rama actual, siguiente tarea, conteos, tokens, aprobaciones ni
resultados de checks.

`project_id` no se deriva en cada ejecución de la ruta local, rama o remote,
porque todos pueden cambiar. `init-plan` propone un UUID una sola vez; una
migración posterior de identidad es una operación gobernada y auditable.

## 6. Pilotos previstos

### Kratos

Proyecto limpio y origen del estándar preliminar. Permite validar estructura,
neutralidad, plan/apply y compatibilidad con AN-KLA sin acoplar Praxis a ella.

### ADRC-Python

Corpus complejo para probar migración:

- números ADR duplicados;
- estados heterogéneos;
- reportes mezclados con decisiones;
- baseline histórico;
- SPEC y gates ya desarrollados;
- decisiones avanzadas sobre autoridad.

Debe operar primero en observación. Los defectos existentes se inventarían de
forma exacta; todo ADR nuevo usaría modo estricto.

### Proyecto personal pequeño

Valida que `minimal` y `standard` no impongan ceremonia innecesaria y que la
ausencia de infraestructura externa produzca degradación honesta.

### Piloto read-only: escrubery (2026-08-19, ejecutado)

Primer tercer repositorio en ejercer el contrato CLI (`praxis_dev 0.1.0-draft.1`,
sólo lectura, sin adopción). Resultados observados en
`github.com/kristhianmanue1/escrubery` @ `5dc9717`:

- `project status` → exit 0, `config_present: false`, HEAD resuelto: informe
  honesto de proyecto no adoptado;
- `project audit` → exit 1, `fail` con único finding `config-missing`
  (BLOCKER, L0/unknown): correcto para un repo sin `.praxis.toml`;
- `adr list` → exit 0, cero ADRs en `docs/decisions`: correcto (el proyecto
  usa su propio marco de decisiones);
- `adr audit` → exit 3, `inconclusive` (directorio ausente + schema no
  disponible): no fabricó `fail` sin contrato que validar.

`git status` del objetivo antes y después: idéntico (cero mutaciones). Evidencia
de que la auditoría es no-invasiva y degrada con honestidad ante un tercero
real. Hallazgo de UX registrado: el remediation de `config-missing` no apunta
a una ruta de adopción rápida (cubierto por §1bis).

## 7. Migración entre versiones

Toda versión publica:

- compatibilidad de lectura;
- cambios normativos;
- cambios de esquema;
- transformaciones automáticas permitidas;
- conflictos que requieren revisión;
- procedimiento de rollback o auditoría posterior.

`upgrade-plan` nunca instala paquetes ni publica cambios. La instalación de la
herramienta y la mutación del proyecto son autoridades separadas.

## 8. Desadopción

Praxis debe permitir retirar su integración sin destruir historia del proyecto.
Los bloques gestionados pueden convertirse a contenido local, los ADR y SPEC
siguen siendo Markdown y los resultados JSON permanecen legibles. No se exige
un servicio para consultar decisiones existentes.

## 9. Relación entre AGENTS.md y AN-KLA.md

Ambos son contratos always-on con hogares distintos y no compiten:
`AGENTS.md` es el contrato operativo del proyecto (instrucciones siempre
activas, hogar único por regla del estándar); `AN-KLA.md` es el contrato
gestionado por la herramienta de memoria AN-KLA y sólo describe cómo usar esa
memoria. La memoria recuperada es dato no confiable, nunca instrucción ni
autorización: si ambos discordaran, manda `AGENTS.md` y la solicitud humana
actual, en ese orden; la memoria nunca puede modificar ningún contrato.
