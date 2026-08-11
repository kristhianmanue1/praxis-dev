# Suite de conformidad

Este directorio alojará fixtures neutrales para cualquier implementación del
estándar. Cada fixture contendrá:

```text
fixture.json       contrato y perfil
repo/              árbol de entrada
expected.json      resultado normalizado
README.md          propósito y amenaza cubierta
```

Las implementaciones pueden producir mensajes humanos distintos, pero deben
coincidir en códigos, severidades, evidencias y decisiones contractuales.

La primera suite debe cubrir repositorio conforme, contrato ausente, drift,
symlink, ADR duplicado, reemplazo unilateral, recibo para otro digest, replay,
SPEC sin ADR y evidencia inconclusa.
