# Distribución de Praxis mediante Homebrew

## 1. Decisión de distribución

Praxis Dev se desarrolla en `kristhianmanue1/praxis-dev` y se instala para uso
transversal mediante Homebrew. Los repositorios consumidores no copian el motor
ni crean un entorno virtual propio; sólo conservan su `.praxis.toml`, contratos
y artefactos gobernados.

Convenciones:

| Elemento | Nombre |
|---|---|
| Producto fuente | `kristhianmanue1/praxis-dev` |
| Tap previsto | `kristhianmanue1/homebrew-tap` |
| Fórmula | `praxis` |
| Comando | `praxis` |
| Runtime | Homebrew `python@3.12` |
| Paquete importable | `praxis_dev` |
| Artefacto inicial | `praxis.pyz` dentro de tarball de release |

Instalación prevista:

```bash
brew install kristhianmanue1/tap/praxis
praxis --version
praxis doctor
```

La instalación plenamente cualificada limita la confianza a la fórmula
solicitada. No se requiere confiar en todo el tap.

## 2. Por qué un tap separado

Homebrew resuelve `usuario/tap` hacia el repositorio
`usuario/homebrew-tap`. Mantener la fórmula publicada en ese repositorio:

- sigue la convención nativa de Homebrew;
- separa código fuente de metadatos de distribución;
- permite añadir otras fórmulas personales sin convertir Praxis en un tap;
- mantiene releases y tags de Praxis como fuente del artefacto;
- permite probar y actualizar la fórmula sin cambiar el estándar.

`praxis-dev` conserva la plantilla y los checks del contrato de empaquetado. La
fórmula publicada, con versión y checksum concretos, vive canónicamente en el
tap.

## 3. Artefacto de release

La primera versión producirá un zipapp autocontenido:

```text
praxis-<version>.tar.gz
├── praxis.pyz
└── LICENSE

SHA256SUMS                 archivo de release separado
```

`SHA256SUMS` contiene el hash del tarball final; no se incluye dentro del mismo
tarball para evitar una referencia circular. `praxis.pyz` contiene el paquete y
entrypoint, pero no el intérprete. La fórmula
declara `depends_on "python@3.12"` y crea un wrapper que usa la ruta estable de
esa dependencia. Esto evita depender del Python del sistema o del `PATH` del
usuario.

Mientras el producto no tenga dependencias externas, zipapp reduce superficie
de suministro y funciona en Apple Silicon, Intel y Linuxbrew con el mismo
contenido. Si aparecen dependencias nativas, esta decisión debe revisarse; no
se ocultarán dentro del artefacto sin declarar plataforma y procedencia.

## 4. Fórmula

La plantilla vive en `packaging/homebrew/praxis.rb.tpl`. En cada release, el
pipeline sustituye exclusivamente versión, URL y SHA-256 y propone el diff en
el tap. La fórmula:

- descarga una release etiquetada, nunca `main`;
- verifica SHA-256;
- depende de `python@3.12`;
- instala el artefacto en `libexec`;
- expone sólo `bin/praxis` y ejecuta Python con `-I` para aislar variables y
  paquetes del usuario;
- ejecuta una prueba funcional mínima;
- no usa APIs privadas de Homebrew para virtualenv;
- no descarga paquetes durante instalación.

## 5. Cadena de release

```text
commit revisado
  → tag autorizado
  → build reproducible de praxis.pyz
  → tests sobre artefacto
  → release con hashes
  → PR de fórmula ligado al tag y SHA
  → brew audit/test/install desde fuente
  → publicación del tap
```

El pipeline no se autoautoriza por pasar tests. Tag, release y actualización de
fórmula son transiciones protegidas con autoridad y evidencias separadas.

## 6. Reproducibilidad

El build debe fijar:

- Python 3.12 y versión de herramientas de empaquetado;
- orden estable de archivos;
- timestamps normalizados mediante `SOURCE_DATE_EPOCH` o equivalente;
- permisos de entradas;
- exclusión de cachés, tests temporales y secretos;
- hash SHA-256 del pyz y tarball.

Un job independiente reconstruye el tag y compara hashes antes de actualizar la
fórmula. Si no son idénticos, el release queda inconcluso.

## 7. Pruebas Homebrew

Antes de publicar:

```bash
brew audit --strict kristhianmanue1/tap/praxis
brew install --build-from-source kristhianmanue1/tap/praxis
brew test kristhianmanue1/tap/praxis
praxis --version
```

La prueba de fórmula debe ejecutar además una auditoría read-only sobre un
fixture mínimo y comprobar código de salida/JSON, no sólo `--help`.

## 8. Actualizaciones y compatibilidad

Homebrew controla instalación, upgrade y desinstalación. Praxis:

- no se autoactualiza;
- puede avisar de incompatibilidad, pero no ejecutar `brew`;
- conserva compatibilidad de lectura según el estándar;
- exige `project upgrade-plan/apply` para cambiar archivos del repositorio;
- separa actualizar el binario de actualizar un proyecto consumidor.

Una actualización de fórmula nunca modifica automáticamente repositorios.

## 9. Desarrollo local

Durante F0 se usa explícitamente:

```bash
/opt/homebrew/bin/python3.12 scripts/check_repo.py
/opt/homebrew/bin/python3.12 -m unittest discover -s tests -v
```

Cuando exista el paquete, el desarrollo se realizará en un entorno 3.12 del
repositorio. Ese entorno no es el mecanismo de distribución a consumidores.

## 10. Seguridad y límites

- Un tap ejecuta código Ruby con privilegios del usuario: la fórmula se revisa.
- El checksum prueba integridad contra la fórmula, no legitimidad del autor.
- El tap no es proveedor de autoridad para aceptar ADR de consumidores.
- Una cuenta que publica la fórmula no debe compartir credenciales con agentes.
- No se usa `head` para instalaciones gobernadas.
- No se promete soporte Windows mediante Homebrew; se diseñará otro adaptador
  de distribución si aparece esa necesidad.

## Referencias oficiales

- [How to Create and Maintain a Tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)
- [Taps y modelo de confianza](https://docs.brew.sh/Taps)
- [Bottles](https://docs.brew.sh/Bottles)
- [API Python Virtualenv de Homebrew](https://docs.brew.sh/rubydoc/Language/Python/Virtualenv.html)
