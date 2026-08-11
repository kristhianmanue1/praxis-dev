# Arquitectura de Praxis Dev

## 1. Enfoque

Praxis Dev es un **monorepo modular de contratos**, no un servicio central. El
nucleo determina cómo descubrir, auditar y mutar gobernanza; los módulos
especializan dominios. La implementación de referencia deberá ser invocable
como CLI y biblioteca, pero los esquemas y fixtures permitirán implementaciones
en otros lenguajes.

```text
                           ┌─────────────────────┐
                           │ Solicitud / CI / UI │
                           └──────────┬──────────┘
                                      │
                              ┌───────▼───────┐
                              │ CLI `praxis` │
                              └───────┬───────┘
                                      │
                  ┌───────────────────▼───────────────────┐
                  │ Core: config, identidad, audit, plan │
                  └──────┬───────────┬───────────┬────────┘
                         │           │           │
                  ┌──────▼───┐ ┌────▼────┐ ┌────▼────────┐
                  │ Políticas│ │ ADR/SPEC│ │ Evidencia   │
                  └──────┬───┘ └────┬────┘ └────┬────────┘
                         │           │           │
                  ┌──────▼───────────▼───────────▼────────┐
                  │ Autoridad y adaptadores subordinados │
                  └───────────────────────────────────────┘
```

## 2. Capas

### 2.1 Contratos normativos

Documentos y manifiestos versionados definen semántica, invariantes y perfiles.
Son la fuente humana canónica. Cada regla bloqueante debe tener representación
machine-readable o un gate claramente identificado antes de ser promovida.

### 2.2 Esquemas

JSON Schema describe planes, recibos, resultados y metadatos. Los esquemas no
otorgan autoridad: validan forma, no procedencia ni firma.

### 2.3 Motor determinista

El futuro paquete `praxis_dev`, implementado para Python 3.12, resolverá
configuración, generará fingerprints, evaluará reglas y producirá resultados.
Los contratos y fixtures no dependen del lenguaje. El motor no invocará un LLM para decidir si un
contrato pasa. Un módulo puede aceptar una clasificación asistida por IA como
evidencia, pero la política de fallo debe permanecer explícita.

### 2.4 Adaptadores

Traducen identidad y evidencia de GitHub, GitLab, hosts de agentes, passkeys u
otras herramientas. Nunca sustituyen el núcleo ni convierten capacidades
declaradas en capacidades verificadas.

## 3. Árbol canónico del repositorio producto

```text
AGENTS.md                    contrato siempre activo
README.md                    entrada humana
.praxis.toml                 adopción local del propio estándar
docs/
  fundamentos.md             intención y límites
  estandar.md                reglas normativas
  arquitectura.md            componentes y dependencias
  modelo-autoridad.md        frontera de confianza
  contrato-cli.md            interfaz observable
  conformidad.md             perfiles, niveles y gates
  adopcion.md                bootstrap y migración
  roadmap.md                 plan durable inicial
  decisions/                 ADR, sólo decisiones
  modulos/                   contratos especializados
schemas/                     contratos de datos
standards/praxis/v1/         manifiesto de la versión
templates/                   assets para proyectos consumidores
adapters/                    especificaciones/implementaciones por host
conformance/                 fixtures neutrales
scripts/                     gates del propio repo
tests/                       pruebas del producto y sus gates
```

## 4. Árbol mínimo de un consumidor

```text
AGENTS.md
.praxis.toml
docs/
  politica-agentes.md
  decisions/
  specs/                     si el módulo SPEC está activo
scripts/                     gates locales o wrappers
```

El contenido común puede proyectarse como bloque gestionado con hash. Las
extensiones del proyecto viven fuera del bloque. Una actualización debe
inspeccionar, producir plan y rechazar drift no reconciliado.

## 5. Identidad del proyecto

La ruta o el nombre del directorio no son identidad suficiente. Un plan debe
usar una identidad estable declarada durante adopción y, cuando exista Git,
registrar también remote normalizado y commit observado. Mover un checkout no
debe cambiar la identidad; apuntar el plan a otro repo sí debe fallar.

## 6. Consistencia y concurrencia

Praxis usa control optimista:

1. `*-plan` observa estado y calcula fingerprint.
2. El humano o sistema autorizado revisa el plan.
3. `*-apply` vuelve a observar el estado.
4. Si cambió cualquier precondición, falla y exige replanificar.

Esto evita locks persistentes, pero no elimina colisiones entre ramas. Los
gates de merge deben volver a comprobar unicidad contra la base actualizada.
Los identificadores no requieren continuidad sin huecos; sí unicidad y no
reutilización.

## 7. Seguridad de archivos

Para destinos gobernados, el motor debe:

- resolver rutas dentro de la raíz del proyecto;
- rechazar `..`, rutas absolutas no previstas y escapes por symlink;
- crear archivos nuevos de forma exclusiva;
- preservar permisos declarados;
- no seguir enlaces en operaciones sensibles;
- limitar rollback a archivos creados por la invocación actual;
- reportar resultado incierto después de una interrupción.

No se promete atomicidad multiartefacto frente a caída de energía hasta contar
con un protocolo explícito de journal o rename transaccional.

## 8. Fronteras de extensión

- Un perfil agrega requisitos; no relaja invariantes del Core.
- Un proyecto agrega reglas de dominio; no las presenta como universales.
- Un adaptador aporta evidencia; no cambia estados directamente.
- Un módulo puede depender del Core y de contratos declarados; se evitan ciclos.
- La memoria puede enlazar artefactos; no los reemplaza ni autoriza mutaciones.
