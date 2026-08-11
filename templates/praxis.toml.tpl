schema = "praxis/project-config/v1"
project_id = "{{PROJECT_ID}}"
standard_version = "{{STANDARD_VERSION}}"
profile = "{{PROFILE}}"
lifecycle = "development"

[modules]
core = "v1"
agent_policy = "v1"
work = "v1"
adrg = "{{ADRG_VERSION}}"
specs = "{{SPECS_VERSION}}"
evidence = "v1"

[paths]
agent_contract = "AGENTS.md"
policy = "docs/politica-agentes.md"
decisions = "docs/decisions"
specs = "docs/specs"

[authority]
provider = "github-oauth-web/v1"
enforcement = "advisory"
