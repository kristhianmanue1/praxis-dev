<!-- praxis:adr
{
  "schema": "praxis/adr-metadata/v1",
  "id": "ADR-0003",
  "title": "Procedimiento de la primera promoción humana del estándar",
  "status": "proposed",
  "created_at": "2026-08-19T01:40:00Z",
  "origin": "agent_assisted",
  "authors": ["opencode"],
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
      "at": "2026-08-19T01:40:00Z",
      "authority_receipt": null,
      "authority_receipt_sha256": null
    },
    {
      "from": "draft",
      "to": "proposed",
      "at": "2026-08-19T01:40:00Z",
      "authority_receipt": null,
      "authority_receipt_sha256": null
    }
  ]
}
-->

# ADR-0003: Procedimiento de la primera promoción humana del estándar

## Contexto y problema

`docs/estandar.md` §10 exige que toda promoción del estándar incluya una
"decisión humana explícita de promoción" y prohíbe que la candidata se
autoapruebe. La matriz de `docs/modelo-autoridad.md` §7 reserva la
administración del estándar para autoridad protegida, que aún no existe
(F4). El repositorio opera hoy en `lifecycle=development` con enforcement
`advisory` y sin adaptador de autoridad.

Esto crea una brecha operativa: existe el requisito de una decisión humana,
pero no existe ningún procedimiento que defina quién la toma, sobre qué
artefacto exacto, con qué evidencia mínima, ni cómo se registra de forma
verificable. Sin ese procedimiento, la primera promoción sería una acción
informal imposible de auditar, o quedaría bloqueada indefinidamente
esperando capacidad técnica (F4) que el estándar mismo no exige para el
bootstrap.

## Alcance y no objetivos

Este ADR define el procedimiento mínimo de la primera promoción humana de
`praxis/project-governance` (de `draft` a candidata) y su registro. No
implementa autoridad criptográfica, no crea el adaptador F4, no modifica la
matriz de autoridad ni los perfiles. La aceptación de este mismo ADR es una
decisión de repositorio (transición ADRG) y sigue los gates ADRG existentes;
no es una promoción de estándar y por eso no requiere etiqueta ni registro
de promoción. Esa distinción es estructural, no una exención: si alguien
pretendiera usar la aceptación de un ADR como promoción del estándar, estaría
confundiendo dos autoridades que este documento mantiene separadas.

## Drivers e invariantes

- La promoción es y sigue siendo humana; ningún agente puede ejecutarla,
  delegarla ni atestiguarla con datos autodeclarados.
- La decisión se toma sobre un digest exacto (commit), no sobre una rama
  móvil ni un estado "aproximado".
- El registro debe ser verificable con las herramientas existentes del repo
  (Git, gates, audit) sin infraestructura nueva.
- La ausencia de adaptador de autoridad NO convierte la promoción en
  informal: la degrada honestamente a lo que hoy se puede probar (identidad
  de cuenta Git + revisión adversarial registrada), con su limitación
  documentada.

## Opciones consideradas

### A. Esperar a F4 (autoridad con recibos)

Correcto para `high-assurance`, pero bloquea el bootstrap del propio
estándar en una capacidad que el mismo estándar no exige para
`lifecycle=development`. Convierte la deuda documental en bloqueo
permanente.

### B. Decisión informal (commit de maintainer)

Es lo que haría cualquier proyecto, pero no satisface §10: sin procedimiento
ni registro estructurado, la "decisión humana explícita" se reduce a
confianza en la historia de Git, exactamente lo que el estándar pide
superar.

### C. Procedimiento mínimo registrable con evidencia actual (elegida)

Definir artefacto exacto, evidencia mínima, rol humano y registro
estructurado del acto de promoción, usando sólo lo que existe hoy: commit
digest, revisión adversarial documentada, y un registro de promoción como
archivo verificable por gates.

## Decisión

La primera promoción humana del estándar (y de este ADR) exige, en orden:

1. **Candidata congelada:** un commit etiquetado `vX.Y.Z-rc.N` cuyo digest
   sea el objeto exacto de la decisión. La etiqueta es inmutable; cualquier
   cambio exige nueva etiqueta y nueva decisión.
2. **Evidencia mínima adjunta en el cuerpo de la etiqueta** (o archivo
   referenciado por digest en él):
   - resultado de `scripts/check_repo.py` en el commit exacto;
   - resultado de la suite de tests completa;
   - al menos una revisión adversarial independiente documentada (documento
     con hallazgos y decisión `proceed`/`block`), realizada por un agente o
     humano que no sea autor del cambio ni preparador de la evidencia;
   - registro de pilotos read-only existentes (hoy: escrubery 2026-08-19).
3. **Rol humano:** sólo una persona listada como `decision_owners` en la
   metadata de los ADR del estándar (hoy: `Kris Nova`) puede ejecutar la
   promoción. Ese campo es el hogar vigente de la propiedad de decisión;
   si el estándar adquiere un registro formal de owners, el ADR que lo cree
   actualizará esta referencia. Un agente puede preparar 1 y 2, nunca 3.
4. **Acto de promoción:** el humano crea la etiqueta anotada firmando con su
   identidad Git real y añade un registro `docs/releases/promotion-<tag>.md`
   con: digest del commit, lista de evidencia con sus digests, identidad
   del humano (cuenta), fecha, y una declaración explícita de que promueve
   esa candidata exacta.
5. **Verificación posterior:** `adr audit` y los gates deben pasar sobre el
   commit promovido; el registro de promoción es auditable por cualquier
   tercero con acceso al repo.

**Limitación declarada:** sin F4, la identidad humana descansa en la cuenta
Git y la firma del tag; esto NO es un recibo de alta garantía y no habilita
`lifecycle=production`, perfiles `controlled`/`sealed` ni conformidad de
producción. El paso a estable (`1.0.0`) exigirá F4 o un ADR que endurezca
este procedimiento.

## Consecuencias

Positivas:

- La brecha "requisito sin procedimiento" queda cerrada sin inventar
  autoridad técnica inexistente.
- Cualquier observador puede verificar qué digest fue promovido, con qué
  evidencia y por quién.

Negativas:

- El procedimiento es deliberadamente incómodo (etiqueta anotada + registro)
  para que la promoción sea un acto raro y deliberado, no un push más.
- Mientras F4 no exista, la identidad humana descansa en la cuenta Git:
  falsificable por quien controle la cuenta o la forja.

Neutrales:

- Deuda: cuando F4 exista, este ADR deberá ser sustituido por uno que
  reemplace la identidad de cuenta por recibos verificables.

## Seguridad, migración y reversibilidad

- **Seguridad:** el vector dominante es la suplantación de la cuenta Git del
  `decision_owner`; se mitiga exigiendo tag anotado (no lightweight),
  evidencia con digests y revisión adversarial independiente, pero no se
  elimina hasta F4. Ningún agente puede ejecutar el paso 3: preparar
  evidencia no es promover.
- **Privacidad:** el registro de promoción expone la identidad de la cuenta
  del humano; es deliberado (rendición de cuentas) y público.
- **Migración:** la primera promoción `draft→rc` no elimina contenido; los
  ADR existentes conservan su estado. El paso `rc→stable` exigirá F4 o un
  ADR endurecedor, nunca una edición de este archivo.
- **Reversibilidad:** una promoción no se "deshace"; se revoca mediante un
  ADR de retirada que referencia el digest promovido y una nueva etiqueta.
  La etiqueta original nunca se reescribe ni se borra.

## Confirmación

- `python3.12 -m praxis_dev adr audit` pasa sobre el commit promovido.
- `python3.12 scripts/check_repo.py` y la suite completa pasan sobre el
  digest exacto de la etiqueta.
- El registro `docs/releases/promotion-<tag>.md` existe, cita el digest del
  commit y los digests de cada evidencia.
- `git tag -v <tag>` verifica la firma. Si el promotor no firma, el registro
  de promoción DEBE declarar "promoción sin firma" y la revisión adversarial
  debe señalarlo como riesgo aceptado; la firma no es opcional en silencio.
- El registro de promoción no tiene aún un gate automático de estructura
  (deuda declarada); su verificación hoy es manual y reproducible.
- Cualquiera puede reproducir 1–2 clonando el digest y ejecutando los
  checks localmente.

## Relaciones con ADR, SPEC e implementación

- **ADR-0001** (plataforma modular): este ADR es una especialización de su
  principio de autoridad externa al agente.
- **ADR-0002** (validación cerrada): la evidencia mínima usa
  exactamente los gates que ese ADR justificó.
- **Implementación:** no requiere código nuevo; usa Git, gates y audit
  existentes. Cuando `adr new-plan/new-apply` (F3) exista, el registro de
  transición de un ADR aceptado podrá ligarse al recibo de promoción.
- **SPEC:** ninguna; este ADR no cambia comportamiento observable del CLI.

## Disparadores de revisión

- F4 entrega el primer adaptador de autoridad con recibos.
- Algún proyecto consumidor declara conformidad de producción.
- La propiedad del repositorio cambia de manos o de forja.
- Un incidente compromete la cuenta Git de un `decision_owner`.
- Se propone una versión `1.0.0` estable.

## Referencias y evidencia

- `docs/estandar.md` §10 (requisitos de promoción) y §9 (excepciones).
- `docs/modelo-autoridad.md` §7 (matriz de administración protegida).
- `docs/roadmap.md` F4 (autoridad progresiva, pendiente).
- Piloto read-only escrubery registrado en `docs/adopcion.md` §6
  (2026-08-19, commit `5dc9717` del objetivo).
- Ciclo gobernado `init-plan/init-apply` implementado en `praxis_dev`
  (commits `97568b9`, `08d355d`) con ronda adversarial documentada en el
  segundo.

## Estado

Propuesto. Su aceptación sigue este mismo procedimiento: revisión
adversarial + decisión humana de un `decision_owner`.
