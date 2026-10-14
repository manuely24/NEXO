# ADR 0002: Clasificación de datos y modos de autonomía

## Clases de datos (D11)
- LOCAL: nunca sale de la máquina (claves, tokens, finanzas). Es el valor por defecto.
- CONFIDENTIAL: solo sale con autorización explícita por fuente (correo, documentos).
- CLOUD_OK: puede enviarse al proveedor del LLM (código, consultas generales).

Fase 0 solo define el tipo. La aplicación automática de esta clasificación
es responsabilidad del Policy Engine (Fase 1).

## Modos de autonomía (D14)
1 Asistente, 2 Ejecutor, 3 Automatización, 4 Agente, 5 Sistema personal.
Por defecto Nexo arranca en modo 2 y sube solo si lo configuras. El modo 5 es la
visión a largo plazo y requiere sensores y dispositivos (fases 5-8).
