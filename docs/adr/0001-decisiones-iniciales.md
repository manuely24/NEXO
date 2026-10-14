# ADR 0001: Decisiones iniciales

Estado: aprobado (pendiente de tu confirmación en D11, D12, D14)

| # | Decisión |
|---|---|
| D1 | Núcleo en Python (3.12 recomendado, mínimo 3.11) |
| D2 | LLM por API tras una interfaz intercambiable |
| D3 | SQLite como fuente de verdad; Markdown para conocimiento editable; JSON solo config |
| D4 | El motor de políticas (código) decide permisos, nunca el LLM |
| D5 | Contenido externo = datos no confiables; acciones derivadas suben de nivel |
| D6 | ActionRequest/Result tipados; verificador obligatorio si riesgo > INFO |
| D7 | Sin agentes al inicio; luego perfiles de configuración |
| D8 | CLI primero; luego web local; sin Electron |
| D9 | Portable vía OS Adapter; empezar en Windows |
| D10 | APIs/CLIs primero; automatización de UI como último recurso |
| D11 | Clases de datos: LOCAL / CONFIDENTIAL / CLOUD_OK (ver ADR 0002) |
| D12 | Campusland: organizador y tutor; la entrega es acción separada con confirmación |
| D13 | Bucle propio, sin frameworks de agentes |
| D14 | Modos de autonomía 1-5 (ver ADR 0002) |
