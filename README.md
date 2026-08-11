# Praxis Dev

**Estado:** diseño fundacional · **Versión del estándar:** `0.1.0-draft.0`

Praxis Dev es un estándar ejecutable de gobernanza para proyectos de software
asistidos por agentes de IA. Convierte políticas, decisiones, contratos de
trabajo y evidencia en reglas verificables, neutrales respecto del modelo y del
proveedor.

El proyecto no es un orquestador de agentes, un motor de memoria ni una
plataforma de colaboración. Su responsabilidad es definir y comprobar **cómo se
gobierna un repositorio**: qué puede hacer un agente, qué requiere autoridad
humana, cómo se registran decisiones y qué evidencia permite cerrar trabajo.

## Objetivos

- Ofrecer un contrato común para proyectos personales y equipos pequeños.
- Separar solicitud, autoridad, decisión, ejecución y evidencia.
- Mantener un único hogar canónico para cada tipo de información.
- Proporcionar auditoría de sólo lectura y mutaciones mediante `plan/apply`.
- Estandarizar políticas para agentes, ADR, SPEC y revisión proporcional.
- Permitir perfiles de aseguramiento sin imponer la misma ceremonia a todo.
- Producir resultados deterministas consumibles por humanos, agentes y CI.

## Límites

Praxis Dev compone herramientas existentes; no las absorbe:

| Sistema | Responsabilidad |
|---|---|
| Praxis Dev | Gobernanza ejecutable del proyecto |
| Kratos | Coordinación y conocimiento del ecosistema |
| AN-KLA | Memoria y continuidad privada por proyecto |
| Ágora | Medio compartido para externalizar y transformar artefactos |
| CAGF | Gobernanza constitucional y arbitraje |
| Git/forja | Historial, revisión, protección de ramas y publicación |
| Herramientas del proyecto | Tests, lint, build, seguridad y despliegue |

## Arquitectura inicial

```text
Praxis Dev
├── Core                 precedencia, hogares, plan/apply y evidencia
├── Agent Policy         autoridad y forma de trabajo de agentes
├── Work Governance      objetivos, tareas, contratos y cierre
├── ADRG                 decisiones arquitectónicas gobernadas
├── SPEC Governance      comportamiento normativo y trazabilidad
├── Evidence             checks reproducibles y procedencia
├── Authority            transiciones protegidas y recibos verificables
└── Adapters             traducción hacia hosts, forjas y proveedores
```

## Navegación

- [Fundamentos](docs/fundamentos.md)
- [Estándar normativo](docs/estandar.md)
- [Arquitectura](docs/arquitectura.md)
- [Modelo de autoridad](docs/modelo-autoridad.md)
- [Contrato de CLI](docs/contrato-cli.md)
- [Distribución mediante Homebrew](docs/distribucion-homebrew.md)
- [Conformidad y perfiles](docs/conformidad.md)
- [Gobernanza de ADR](docs/modulos/adrg.md)
- [Política de trabajo de agentes](docs/modulos/politica-agentes.md)
- [Relación ADR–SPEC](docs/modulos/specs.md)
- [Adopción y migración](docs/adopcion.md)
- [Roadmap](docs/roadmap.md)

## Verificación local

Esta fase no implementa todavía el CLI de producto `praxis`. El repositorio se
autoverifica con Python estándar:

```bash
python3.12 scripts/check_repo.py
python3.12 -m unittest discover -s tests -v
```

## Estado honesto

Los documentos y esquemas de esta versión son una propuesta fundacional. No
existe aún un adaptador de autoridad, no hay garantías criptográficas y ningún
proyecto consumidor debe declarar conformidad de producción. La promoción a
una versión estable requiere revisión humana, pruebas de conformidad y pilotos
en repositorios reales.
