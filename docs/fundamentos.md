# Fundamentos de Praxis Dev

**Versión:** `0.1.0-draft.1` · **Estado:** propuesta fundacional

## 1. Problema

Los agentes de IA pueden producir código y documentación rápidamente, pero esa
velocidad no resuelve cuatro preguntas de gobernanza:

1. ¿Qué instrucciones tienen precedencia?
2. ¿Qué cambios puede ejecutar un agente y cuáles requieren otra autoridad?
3. ¿Qué artefacto conserva la decisión, el contrato y la evidencia?
4. ¿Cómo se demuestra que el estado actual coincide con lo declarado?

Sin respuestas ejecutables aparecen patrones recurrentes: reglas duplicadas,
planes convertidos en memoria, ADR usados como reportes, aprobaciones textuales
falsificables, índices manuales, estados contradictorios y agentes que validan
su propio trabajo sin independencia real.

Praxis Dev trata estos problemas como contratos de repositorio, no como
recomendaciones de estilo.

## 2. Propósito

Praxis Dev define un lenguaje común y una implementación de referencia para:

- descubrir la política aplicable;
- auditar un repositorio sin mutarlo;
- planificar cambios contra un estado exacto;
- aplicar sólo el plan autorizado y vigente;
- gobernar decisiones arquitectónicas y especificaciones;
- separar autoridad de contenido autodeclarado;
- recopilar evidencia reproducible;
- adoptar el estándar gradualmente en proyectos existentes.

## 3. Principios

### 3.1 Resultado antes que ceremonia

Cada artefacto debe resolver una necesidad verificable. Una tarea trivial no
requiere ADR, plan durable ni consenso. La gobernanza aumenta con impacto,
irreversibilidad, alcance y sensibilidad.

### 3.2 Componer antes que fusionar

Praxis Dev integra memoria, forjas, CI y agentes mediante contratos. No se
convierte en otro motor de memoria, orquestador o repositorio compartido.

### 3.3 Un hogar canónico

Una afirmación normativa tiene una sola fuente. Los índices y dashboards son
proyecciones derivadas. Si dos archivos deben editarse manualmente para cambiar
el mismo estado, el diseño tiene dos fuentes de verdad.

### 3.4 Evidencia antes que afirmación

Un estado como `implemented`, `verified` o `compliant` requiere checks y
procedencia. La ausencia de evidencia produce `unknown` o `inconclusive`, no un
éxito optimista.

### 3.5 Autoridad separada del candidato

El contenido propone qué hacer; otra señal demuestra quién puede autorizarlo.
Campos como `trusted`, `human_approved` o `verified` no elevan autoridad por sí
mismos.

### 3.6 Fallo cerrado donde importa

Una entrada desconocida no siempre es un error, pero nunca debe degradar una
operación protegida. Para seguridad, publicación, políticas y decisiones
aceptadas, `unknown` bloquea hasta obtener evidencia suficiente.

Durante el ciclo `development`, la autenticación advisory puede degradarse a
`development-unverified` sin bloquear trabajo ordinario. Esa excepción de
ergonomía no convierte el resultado en autoridad, no satisface una transición
protegida y no habilita promoción estable.

### 3.7 Neutralidad de proveedor

Codex, Claude, Gemini, Grok, modelos locales y futuras herramientas son
adaptadores. El estándar se define por comportamiento observable, no por marca
ni por afirmaciones de capacidad.

### 3.8 Estado derivado

Git, tests, manifiestos y herramientas observadas determinan el estado real.
Roadmaps, memoria y documentos históricos no sustituyen esa medición.

## 4. Modelo conceptual

```text
Solicitud actual
      │ fija objetivo, alcance y autoridad disponible
      ▼
Contrato del proyecto
      │ restringe proceso y hogares canónicos
      ▼
Plan ligado a fingerprint
      │ describe una mutación exacta, todavía sin ejecutarla
      ▼
Aplicación gobernada
      │ valida drift, autoridad y precondiciones
      ▼
Evidencia reproducible
      │ prueba el resultado o declara degradación
      ▼
Historial Git / artefactos externos
```

## 5. Objetos principales

| Objeto | Función | No sustituye |
|---|---|---|
| Política | Reglas operativas vigentes | Solicitud actual |
| Perfil | Nivel de aseguramiento | Reglas de dominio |
| Ciclo | Etapa operativa y conducta de enforcement | Perfil de aseguramiento |
| Tarea | Unidad de trabajo cerrable | Decisión arquitectónica |
| Plan | Mutación propuesta contra un estado | Autorización |
| ADR | Porqué y consecuencias de una decisión | SPEC o reporte |
| SPEC | Comportamiento normativo verificable | Plan de implementación |
| Evidencia | Resultado reproducible de checks | Autoridad |
| Recibo | Prueba externa de una transición autorizada | Corrección técnica |
| Adaptador | Traducción a un host/proveedor | Núcleo normativo |

## 6. Alcance inicial

La primera versión cubre proyectos Git de software y artefactos de texto. El
nucleo debe funcionar localmente, sin servicio central, usando formatos
abiertos. Un proveedor de autoridad externo es opcional para auditoría y
trabajo ordinario en `development`, y obligatorio para transiciones de alta
garantía.

Quedan fuera de la primera versión:

- orquestación de ejecuciones de modelos;
- almacenamiento de prompts o conversaciones;
- memoria semántica;
- administración de secretos;
- políticas regulatorias de un dominio específico;
- despliegue y rollback de aplicaciones;
- arbitraje constitucional entre agentes.

## 7. Invariantes fundacionales

1. `audit`, `verify`, `list`, `show` y todo comando `*-plan` no mutan el repo.
2. Todo `*-apply` valida el plan, fingerprint, estado objetivo y drift.
3. La ausencia de un adaptador no concede permisos ni simula éxito.
4. Los estados de decisión e implementación son ortogonales.
5. Las decisiones aceptadas conservan historia y no se reescriben en silencio.
6. Los agentes no pueden convertir sus propias afirmaciones en autoridad.
7. Los contratos machine-readable tienen esquema y versión.
8. Una excepción es acotada, temporal, trazable y nunca redefine la regla.
9. La adopción preserva trabajo existente y falla ante conflictos.
10. Toda salida programática separa datos de mensajes humanos y usa códigos de
    salida documentados.

## 8. Criterio de éxito

Praxis Dev tendrá valor cuando dos proyectos distintos puedan adoptar el mismo
perfil, recibir hallazgos equivalentes ante los mismos defectos y aplicar un
plan sin depender del modelo que lo invocó. La documentación sola no cumple
este criterio: requiere implementación, fixtures de conformidad y pilotos.
