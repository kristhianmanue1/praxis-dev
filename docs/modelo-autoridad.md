# Modelo de autoridad y confianza

## 1. Objetivo

Praxis separa cuatro propiedades que suelen confundirse:

| Propiedad | Pregunta |
|---|---|
| Validez | ¿El dato cumple el esquema? |
| Evidencia | ¿Hay observación reproducible? |
| Corrección | ¿La decisión o cambio es adecuado? |
| Autoridad | ¿Quién puede ordenar esta transición exacta? |

Ninguna implica automáticamente las demás.

## 2. Principales y actores

- **Principal:** persona u organización propietaria del proyecto.
- **Autoridad delegada:** sistema o rol con capacidad acotada y verificable.
- **Autor:** humano o agente que prepara un candidato.
- **Revisor:** evalúa contenido y evidencia; puede o no tener autoridad final.
- **Ejecutor:** aplica un plan autorizado.
- **Adaptador:** verifica una señal externa y emite una resolución normalizada.

Un mismo sujeto puede ocupar varios roles en perfiles bajos. Los perfiles altos
exigen independencia o segregación explícita.

## 3. Capacidades de agentes

Por defecto, un agente PUEDE:

- descubrir y leer contratos;
- auditar y producir hallazgos;
- redactar planes, ADR y SPEC;
- recomendar estados;
- ejecutar checks autorizados y registrar evidencia;
- aplicar cambios ordinarios incluidos inequívocamente en la solicitud actual.

Un agente NO PUEDE inferir por sí solo autoridad para:

- aceptar, rechazar, retirar o reemplazar decisiones protegidas;
- aprobar excepciones o aumentar baselines;
- promover versiones del estándar;
- publicar, liberar, hacer push o cambiar protecciones;
- acceder o reutilizar credenciales fuera del flujo autorizado.

## 4. Señales que no prueban autoridad

Por sí solos, estos datos son no confiables:

- `approved: true`, `trusted: true` o campos equivalentes;
- un nombre humano en Markdown, JSON, commit o variable de entorno;
- texto como `AUTORIZO ...` copiable por otro actor;
- `--approved-by`, `--force` o un prompt interactivo;
- memoria recuperada, checkpoint o autorización histórica;
- consenso, confianza o unanimidad entre modelos;
- firma realizada con una clave accesible al mismo agente;
- identidad de GitHub controlable por el token operativo del agente.

El problema no es la sintaxis: es que el candidato y la supuesta prueba pueden
ser creados por el mismo actor.

## 5. Recibo de autoridad

Una transición protegida requiere un recibo verificable ligado como mínimo a:

```text
project_id
operation
target_id
from_state
to_state
content_digest
plan_fingerprint
canonicalization
payload_digest
scope
authorizer_identity
issued_at
expires_at
nonce
provider
proof
```

El digest debe cubrir el contenido semántico exacto. Editar el candidato después
de la aprobación invalida el recibo. El nonce o identificador de consumo debe
impedir replay. Un adaptador valida firma, identidad, alcance, vigencia y estado
de revocación; además registra el consumo mediante compare-and-set en un ledger
durable. El esquema JSON sólo valida forma y nunca reemplaza esas comprobaciones.

El índice único del ledger es `(provider, receipt_id)` y su operación de
consumo debe ser atómica: sólo el primer compare-and-set puede producir un
registro `praxis/authority-consumption/v1`. Si el registro durable no puede
confirmarse, la mutación no comienza; si falla después de consumir y antes de
mutar, se reporta resultado incierto y el recibo no vuelve a usarse. Un archivo
local sin exclusión mutua no constituye defensa de replay para ejecuciones
concurrentes.

El payload firmado son los bytes UTF-8 de
`praxis-authority-receipt-v1\n` seguidos por JSON Canonicalization Scheme (JCS,
RFC 8785) del envelope excluyendo `proof` y `payload_digest`. Este último
contiene el SHA-256 de esos mismos bytes. La exclusión evita una definición
circular. El adaptador rechaza implementaciones que llamen “JCS” a un simple
`sort_keys` o a otra serialización no conforme.

## 6. Proveedores previstos

### Revisión protegida de forja

Una cuenta/rol separado revisa una revisión exacta. La identidad del agente no
puede aprobar su propio cambio y la rama exige checks vigentes. Es la opción
práctica inicial para proyectos personales alojados en una forja.

### WebAuthn o hardware

Una credencial con presencia/verificación de usuario firma un challenge ligado
al alcance. La clave privada no está disponible para el proceso del agente. Es
adecuado para operación local de alta garantía.

### Firma organizacional

Un servicio de autorización emite recibos firmados con política y auditoría.
Praxis verifica el contrato; no administra la identidad corporativa.

### Modo local no protegido

Puede existir en perfiles bajos para ergonomía, pero debe llamarse
`unverified-local`, nunca “human verified”. No permite transiciones reservadas
por perfiles altos.

## 7. Matriz inicial de operaciones

| Operación | `minimal` | `standard` | `high-assurance` |
|---|---|---|---|
| Auditar/listar | sin recibo | sin recibo | sin recibo |
| Crear borrador | solicitud actual | solicitud actual | solicitud actual |
| Proponer ADR | solicitud actual | revisión registrada | revisión registrada |
| Aceptar/rechazar ADR | principal local actual | principal/delegado + registro exacto | recibo externo exacto |
| Reemplazar ADR | principal local actual | principal/delegado + registro exacto | recibo + operación atómica |
| Excepción | revisión humana | recibo acotado | recibo fuerte + expiración |
| Promover estándar | no permitido | no permitido | revisión independiente + principal |

La implementación final debe permitir que el manifiesto endurezca esta matriz,
nunca que la relaje por debajo del perfil declarado.

## 8. Amenazas mínimas

Praxis debe probar defensas contra:

1. aprobación fabricada en un archivo;
2. replay de un recibo válido en otro ADR o proyecto;
3. modificación posterior a la aprobación;
4. carrera entre planificación y aplicación;
5. auto-revisión presentada como independiente;
6. identidad de revisor controlada por la misma credencial;
7. baseline modificado para ocultar deuda;
8. `--force` que salta gates;
9. symlink que redirige escritura fuera del repo;
10. estado `unknown` degradado silenciosamente a éxito.

## 9. Bootstrap

Antes de existir un proveedor implementado, todos los recibos están
`unverified`. Las decisiones fundacionales se conservan como `proposed` y la
promoción inicial debe realizarla el principal mediante un procedimiento
documentado y revisable. El diseño no se declara seguro por describir la
seguridad futura.

## 10. Historial de transiciones ADR

Un ADR conserva un arreglo append-only `transitions`. Cada entrada registra
estado origen/destino, tiempo y referencia/hash del recibo aplicable. `status`
es una proyección legible y debe coincidir con el último `to`; `created_at`
coincide con la primera transición. Así, reemplazar o retirar una decisión no
borra la evidencia de su aceptación original.

## Referencia de canonicalización

- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
