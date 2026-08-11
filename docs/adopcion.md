# Adopción y migración

## 1. Principio

Adoptar Praxis no significa reemplazar la organización de un proyecto por una
plantilla genérica. Significa declarar un contrato, identificar conflictos y
aplicar únicamente assets compatibles mediante un plan revisado.

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

- `project_id` inmutable, versión y perfil;
- módulos activos;
- rutas canónicas;
- proveedor de autoridad;
- extensiones locales.

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
