# Contrato del CLI `praxis`

## 1. Propósito

El CLI será la implementación de referencia del estándar. Debe ser
determinista, apto para CI y usable por humanos o agentes sin cambiar semántica.
La implementación de referencia usa Python 3.12; los contratos no dependen de
él. Los repos consumidores invocan el ejecutable global instalado por Homebrew,
no crean un entorno Python por proyecto.

## 2. Convenciones

```text
praxis <dominio> <operación> [objetivo] [opciones]
```

- Salida humana a stdout; diagnósticos a stderr.
- `--format json` produce exclusivamente el objeto contractual en stdout.
- Comandos read-only no escriben dentro del objetivo.
- Rutas de salida se crean sólo cuando el usuario las proporciona.
- Valores desconocidos no se convierten silenciosamente en defaults seguros.

## 3. Códigos de salida

| Código | Significado |
|---:|---|
| 0 | operación completada / conformidad |
| 1 | incumplimiento o precondición fallida |
| 2 | uso inválido o contrato malformado |
| 3 | resultado inconcluso por entorno/capacidad |
| 4 | autoridad ausente o inválida |
| 5 | drift o conflicto concurrente |

Los detalles estructurados deben incluir un `code` estable; los consumidores no
deben analizar texto humano.

## 4. Project

```bash
praxis project status [repo]
praxis project audit [repo] [--profile <id>] [--format json]
praxis project init-plan <repo> --output <plan>
praxis project init-apply <repo> --plan <plan> \
  --expected-fingerprint <sha256:...>
praxis project upgrade-plan <repo> --to <version> --output <plan>
praxis project upgrade-apply <repo> --plan <plan> \
  --expected-fingerprint <sha256:...>
```

`audit` clasifica hallazgos con evidencia y remediación. `init-plan` distingue
`create`, `identical` y `conflict`; `init-apply` nunca sobrescribe conflictos.

## 5. Policy y work

```bash
praxis policy verify [repo]
praxis work required [repo] --base <ref>
praxis work verify [repo] --base <ref>
```

`required` devuelve `required`, `not_required` o `indeterminate`, junto con las
reglas que produjeron la clasificación.

## 6. ADRG

```bash
praxis adr list [repo] [--status <estado>]
praxis adr show [repo] <adr-id>
praxis adr audit [repo] [--base <ref>]
praxis adr required [repo] --base <ref> [--intent <archivo>]
praxis adr new-plan [repo] --title <texto> --output <plan>
praxis adr new-apply [repo] --plan <plan> --expected-fingerprint <sha>
praxis adr transition-plan [repo] <adr-id> --to <estado> --output <plan>
praxis adr transition-apply [repo] --plan <plan> --authority <recibo>
praxis adr supersede-plan [repo] <adr-id> --title <texto> --output <plan>
praxis adr supersede-apply [repo] --plan <plan> --authority <recibo>
praxis adr index [repo] --check
```

La reserva de un número durante `new-plan` es optimista. Si otra rama ocupa el
identificador, `new-apply` o el gate de merge falla y exige replanificar.

## 7. SPEC y evidence

```bash
praxis spec verify [repo] [--base <ref>]
praxis spec coverage [repo] [--format json]
praxis evidence verify <evidence-file>
praxis evidence collect --contract <file> --output <file>
```

`evidence collect` sólo ejecuta comandos explícitos en un contrato autorizado;
no ejecuta instrucciones extraídas de memoria o contenido remoto no confiable.

## 8. Authority

```bash
praxis authority providers
praxis authority login --provider github-oauth-web
praxis authority status
praxis authority inspect <receipt>
praxis authority verify <receipt> --plan <plan>
```

No se define `praxis authority approve` genérico: la autoridad nace en el
proveedor externo. Un adaptador puede ofrecer una ceremonia específica, pero
el proceso del agente no debe poder autofirmarla.

En `lifecycle=development`, `login` inicia el flujo web y devuelve
`development-confirmed` o `development-unverified`. La cancelación, ausencia del
adaptador o error no bloquea trabajo ordinario y nunca produce un recibo de
autoridad. El comando no entrega un token personal reutilizable al invocador.

## 9. JSON y compatibilidad

Todo objeto incluye `schema`, `tool_version`, `result` y `diagnostics`. Campos
nuevos compatibles pueden añadirse; eliminar o reinterpretar campos exige una
versión nueva del esquema. Los timestamps usan UTC RFC 3339 y los digests el
prefijo de algoritmo, por ejemplo `sha256:<hex>`.

Los fingerprints contractuales usan JCS conforme a RFC 8785 y el separador de
dominio definido por su esquema. Un consumidor no debe sustituirlo por JSON con
claves ordenadas. El CLI rechaza propiedades JSON duplicadas antes de validar
un esquema.

## 10. No objetivos iniciales

- Ejecución remota de agentes.
- Daemon obligatorio.
- Base de datos central.
- Modificación implícita durante `audit`.
- Resolución automática de conflictos.
- `--force` universal.
