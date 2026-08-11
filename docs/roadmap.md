# Roadmap fundacional

**Estado:** propuesta de implementación; no representa progreso ejecutado.

## F0 — Fundación documental

Entregables:

- alcance, estándar, arquitectura y autoridad;
- contratos ADRG y SPEC;
- manifiesto y esquemas iniciales;
- plantillas de adopción;
- gate local del repositorio;
- ADR-0001 propuesto.

Cierre: archivos coherentes, JSON/TOML válidos, tests del gate y revisión
humana de la dirección.

## F1 — Auditoría read-only

Entregables:

- paquete `praxis_dev` y CLI `praxis`;
- artefacto reproducible `praxis.pyz` para Python 3.12;
- `project status/audit`;
- `policy verify`;
- `adr list/show/audit/required`;
- salida JSON estable y códigos de salida;
- fixtures de conformidad positivos y negativos.

Cierre: auditoría repetible sobre Praxis, Kratos y un fixture sintético sin
cambios de hash/mtime en los repos objetivos; instalación de prueba mediante
fórmula Homebrew sobre el artefacto de release exacto.

## F2 — Inicialización gobernada

Entregables:

- `project init-plan/init-apply`;
- identidad estable de proyecto;
- fingerprints canónicos;
- protección de paths, symlinks y drift;
- rollback limitado y reporte de estado incierto.

Cierre: pruebas adversariales de conflicto, carrera y escape de raíz.

## F3 — ADRG mutante

Entregables:

- `adr new-plan/new-apply`;
- transiciones y reemplazo;
- digest del núcleo aceptado;
- índice derivado;
- clasificación `required/not_required/indeterminate`.

Cierre: ningún agente puede aceptar con campos autodeclarados; colisiones y
ediciones posteriores a aprobación fallan.

## F4 — Autoridad progresiva

Entregables:

- interfaz de adaptadores de autoridad;
- proveedor inicial `github-oauth-web/v1` para `lifecycle=development`;
- resultados advisory `development-confirmed | development-unverified`;
- separación entre token personal, proceso del agente y observación devuelta;
- fixtures de cancelación, indisponibilidad, identidad incorrecta y token
  reutilizable expuesto;
- documentación explícita de que OAuth no demuestra WebAuthn ni autoriza un
  digest exacto.

Cierre: el flujo mejora la identificación interactiva sin bloquear desarrollo,
no emite recibos fuertes y no permite conformidad de producción. Los perfiles
`controlled` y `sealed` permanecen como
[deuda futura](https://github.com/kristhianmanue1/praxis-dev/issues/10).

## F5 — SPEC y evidencia

Entregables:

- validación de SPEC y relación ADR–SPEC;
- drift y cobertura semántica mínima;
- contrato de evidencia reproducible;
- integración CI neutral.

Cierre: cambios de contrato sin SPEC/ADR aplicables fallan según perfil.

## F6 — Pilotos y versión candidata

Entregables:

- adopción en Kratos;
- auditoría de migración de ADRC-Python;
- piloto `minimal` en proyecto pequeño;
- documentación de compatibilidad;
- revisión independiente del estándar completo.

Cierre: promoción humana a `1.0.0-rc.1`, no directamente a estable.

## Riesgos transversales

- convertir el estándar en monolito;
- crear una segunda fuente de verdad mediante índices manuales;
- presentar GitHub OAuth de desarrollo como autoridad de alta garantía;
- exigir infraestructura desproporcionada a proyectos pequeños;
- confundir esquema válido con prueba auténtica;
- autoaprobar el estándar con su propia versión candidata.

Cada fase debe mantener módulos separables, contratos abiertos y degradación
explícita.
