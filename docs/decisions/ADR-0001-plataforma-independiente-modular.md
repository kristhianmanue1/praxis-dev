<!-- praxis:adr
{
  "schema": "praxis/adr-metadata/v1",
  "id": "ADR-0001",
  "title": "Praxis Dev como plataforma independiente y modular",
  "status": "proposed",
  "created_at": "2026-08-11T11:02:19Z",
  "origin": "agent_assisted",
  "authors": ["Kratos"],
  "decision_owners": ["Mediador"],
  "assurance_profile": "high-assurance",
  "supersedes": [],
  "superseded_by": null,
  "related": [],
  "decision_core_sha256": null,
  "transitions": [
    {
      "from": null,
      "to": "draft",
      "at": "2026-08-11T11:02:19Z",
      "authority_receipt": null,
      "authority_receipt_sha256": null
    },
    {
      "from": "draft",
      "to": "proposed",
      "at": "2026-08-11T11:02:19Z",
      "authority_receipt": null,
      "authority_receipt_sha256": null
    }
  ]
}
-->

# ADR-0001: Praxis Dev como plataforma independiente y modular

## Contexto y problema

Kratos desarrolló un estándar preliminar para políticas y prácticas de proyectos
asistidos por agentes. Al analizar la gobernanza de ADR apareció la opción de
crear una herramienta separada. Ambas capacidades comparten las mismas
fronteras: autoridad, auditoría, perfiles, evidencia, plan/apply, migración y
adaptadores.

Mantenerlas como productos distintos produciría manifiestos, fingerprints,
excepciones y fuentes de verdad duplicados. Mantenerlas dentro de Kratos
acoplaría un estándar transversal a la identidad y ciclo de un agente concreto.

## Alcance y no objetivos

La decisión cubre el hogar del estándar y su descomposición principal. No elige
lenguaje definitivo, proveedor de autoridad, formato criptográfico ni plan de
publicación.

## Drivers e invariantes

- Reutilización en proyectos personales heterogéneos.
- Neutralidad de agente, modelo y proveedor.
- Una sola frontera de autoridad y una sola configuración.
- Módulos pequeños con adopción proporcional.
- Compatibilidad con herramientas externas sin absorberlas.
- Capacidad de auditar antes de mutar.

## Opciones consideradas

### A. ADRG dentro de Kratos

Reduce tiempo inicial, pero mezcla el producto transversal con la casa de un
agente y dificulta adopción independiente.

### B. Repositorio exclusivo para ADRG

Mantiene foco, pero duplica Core, autoridad, perfiles, adapters y mecanismos de
migración cuando se combine con el estándar general de proyectos.

### C. Plataforma independiente con módulos

Extrae el estándar a Praxis Dev. Core define gobernanza común; Agent Policy,
Work, ADRG, SPEC, Evidence y Authority evolucionan como módulos versionados.
Kratos y ADRC-Python se convierten en consumidores/pilotos.

## Decisión

Elegir la opción C: Praxis Dev será una plataforma independiente de gobernanza
ejecutable. ADRG será un módulo, no un producto aislado. El CLI público será
`praxis`, la configuración `.praxis.toml` y el paquete de referencia
`praxis_dev`.

## Consecuencias

### Positivas

- Evita dos raíces de confianza.
- Permite reutilizar plan/apply y evidencia entre módulos.
- Separa el estándar de la identidad de Kratos.
- Hace posible conformidad neutral por fixtures.
- Mantiene ADRG especializado sin aislarlo del resto del ciclo.

### Negativas

- Crea y mantiene un repositorio adicional.
- Exige disciplina para impedir un monolito.
- Introduce versionado coordinado entre Core y módulos.
- Requiere migrar el estándar preliminar sin copiar fuentes canónicas.

### Neutrales

- Kratos conserva su política local.
- AN-KLA, Ágora y CAGF permanecen como sistemas separados.
- ADRC-Python no se migra automáticamente.

## Seguridad, migración y reversibilidad

La extracción inicial es reversible mientras Praxis permanezca en borrador.
Ningún proyecto debe retirar sus gates vigentes hasta que un perfil Praxis
equivalente pase pruebas. El adaptador de autoridad será externo; el CLI no
almacenará claves privadas.

## Confirmación

La decisión se confirmará cuando:

1. el manifiesto describa módulos sin ciclos;
2. los mismos fixtures produzcan resultados equivalentes en dos proyectos;
3. auditoría read-only no cambie hash ni mtime del objetivo;
4. un plan de Praxis no pueda aplicarse a otro repo;
5. un recibo autodeclarado no pueda aceptar un ADR.

## Relaciones con ADR, SPEC e implementación

No existen ADR previos en Praxis Dev. La implementación del CLI y sus SPEC se
crearán después de que esta dirección sea revisada y aceptada.

## Disparadores de revisión

- Core y ADRG requieren ciclos de versión incompatibles.
- Un consumidor necesita el módulo ADR sin el Core.
- Praxis invade responsabilidades de Ágora, AN-KLA o CAGF.
- La plataforma exige un servicio central para funciones básicas.

## Referencias y evidencia

- Análisis del estándar preliminar en el repositorio Kratos.
- Auditoría read-only del corpus ADR/SPEC de ADRC-Python.
- `docs/fundamentos.md`, `docs/arquitectura.md` y
  `docs/modelo-autoridad.md` de este repositorio.
