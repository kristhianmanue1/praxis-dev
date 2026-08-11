# Adaptadores

Los adaptadores traducen capacidades de hosts, forjas y proveedores de
autoridad al contrato neutral de Praxis.

Cada adaptador debe declarar:

- proveedor y versión observada;
- mecanismo de descubrimiento;
- capacidades verificadas y degradaciones;
- identidad y frontera de credenciales;
- esquemas de entrada/salida;
- fixtures de conformidad superados;
- amenazas y limitaciones.

Un adaptador no cambia reglas del Core, no eleva permisos y no afirma
independencia sólo porque usa otro nombre de modelo o proceso.

Adaptadores candidatos, todavía no implementados:

- hosts: Codex, Claude, Gemini y CLIs locales;
- forjas: GitHub y GitLab;
- autoridad inicial: GitHub OAuth Web Flow advisory para desarrollo;
- autoridad futura: IdP independiente, revisión protegida o WebAuthn;
- memoria: enlace opcional con AN-KLA, sin autoridad derivada.
