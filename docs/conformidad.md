# Conformidad, perfiles y gates

## 1. Tres dimensiones

Praxis distingue **madurez estructural**, **perfil de aseguramiento** y **ciclo
operativo**. Un nivel alto no significa que el proyecto sea seguro; indica qué
partes del contrato están presentes y verificables. El perfil determina qué
controles exige. El ciclo determina si esos controles son advisory o pueden
gobernar operaciones protegidas.

En la versión inicial el único ciclo válido es `development`; no debe
proyectarse como producción aunque alcance L4 estructural.

## 2. Niveles de madurez

| Nivel | Criterio |
|---|---|
| L0 | No existe contrato descubrible |
| L1 | Existe `AGENTS.md`, sin estructura machine-readable completa |
| L2 | Configuración, política y hogares canónicos presentes |
| L3 | Gates ejecutables y referencias coherentes |
| L4 | Módulos del perfil pasan sin BLOCKER/HIGH |

La salida debe reportar nivel, perfil, ciclo y hallazgos por separado.

## 3. Severidad

| Severidad | Significado | Efecto |
|---|---|---|
| BLOCKER | Invalida autoridad, integridad o capacidad de verificar | impide cierre |
| HIGH | Riesgo material o contrato obligatorio ausente | impide conformidad |
| MED | Deuda real con mitigación disponible | corregir o aceptar explícitamente |
| LOW | Mejora no bloqueante | recomendación |
| INFO | Evidencia contextual | ninguno |

## 4. Gates Core

Todo perfil verifica:

- configuración legible y versión soportada;
- rutas requeridas y archivos canónicos;
- ausencia de escapes por symlink;
- referencias locales resolubles;
- límites de tamaño;
- bloques gestionados íntegros;
- inexistencia de estado dinámico prohibido en `AGENTS.md`;
- formatos JSON/TOML válidos;
- salida diferenciada entre fail e inconcluso.

## 5. Gates por módulo

### Agent Policy

- precedencia explícita;
- autoridad actual, no histórica;
- prohibición de secretos y transmisión no autorizada;
- cierre con checks y revisión proporcional;
- degradaciones declaradas.

### Work

- objetivo y criterio de cierre;
- unidad revisable;
- alcance y no objetivos;
- gates aplicables;
- estado derivable o claramente efímero.

### ADRG

- identificador único y no reutilizado;
- estado canónico;
- secciones obligatorias;
- enlaces existentes y recíprocos;
- núcleo aceptado inmutable;
- reemplazo atómico;
- autoridad válida para transiciones protegidas;
- separación de implementación y decisión.

### SPEC

- esquema y versión;
- archivos cubiertos existentes;
- ADR gobernante o excepción justificada;
- comportamiento y checks observables;
- detección de drift;
- ausencia de placeholders en estados promovidos.

### Evidence

- comando/herramienta identificados;
- base/head reproducibles cuando importan;
- código de salida y resultado coherentes;
- artefactos referenciados por hash;
- procedencia explícita.

### Authority

- proveedor permitido;
- firma/prueba válida;
- identidad y alcance suficientes;
- digest y fingerprint exactos;
- vigencia, revocación y no replay;
- consumo compare-and-set durable antes de mutar;
- independencia exigida por el perfil.

En `development`, el gate sólo comprueba que la degradación sea honesta:

- `github-oauth-web/v1` es el proveedor objetivo declarado;
- `enforcement=advisory` permanece visible;
- éxito produce `development-confirmed`, no un recibo fuerte;
- cancelación, fallo o adaptador ausente produce `development-unverified`;
- ambos resultados quedan fuera de conformidad de producción.

## 6. Baselines

Un baseline sirve para migrar deuda histórica, no para redefinir éxito. Debe:

- enumerar defectos exactos, no sólo un conteo;
- impedir crecimiento;
- permitir reducción sin autorización adicional;
- requerir autoridad para ampliación;
- incluir propietario, razón y fecha objetivo;
- excluir nuevos artefactos de la tolerancia.

Un proyecto con baseline puede alcanzar un nivel de adopción, pero la salida
debe conservar el estado `legacy_debt`; no se presenta como corpus limpio.

## 7. Revisión proporcional

| Impacto | Ejemplos | Revisión mínima |
|---|---|---|
| Bajo | texto, refactor sin contrato | auto-revisión + checks |
| Material | capacidad o contrato interno | contexto fresco o segundo revisor |
| Alto | autoridad, política, ADR, esquema público | revisión independiente |
| Crítico | credenciales, publicación, estándar estable | independencia + principal |

La independencia se basa en procedencia verificable, no sólo en nombres de
modelos. Dos ejecuciones del mismo runtime pueden aportar diversidad de lectura,
pero no deben presentarse como independencia fuerte.

## 8. Suite de conformidad

Cada implementación debe pasar fixtures positivos y negativos neutrales:

- repo conforme;
- contrato ausente;
- bloque gestionado alterado;
- plan modificado;
- drift entre plan y apply;
- symlink de escape;
- ADR duplicado;
- reemplazo unilateral;
- recibo válido para otro digest;
- replay;
- SPEC sin ADR;
- evidencia inconclusa;
- capacidad de adaptador ausente.

El fixture describe entrada y salida esperada, no detalles internos del CLI.
