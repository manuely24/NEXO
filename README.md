# Nexo (Fases 1-4)

Asistente personal local para tareas académicas, repositorios, correo y práctica de inglés.
Gemini propone planes; el código determinista autoriza, ejecuta y verifica cada acción.

## Arquitectura

`Planner → Tool Registry → Policy Engine → Executor → Verifier → Event Log`

- El Planner solo propone acciones; riesgo y clase de datos se derivan del registro.
- El Policy Engine valida herramienta, riesgo, rutas, clase de datos y aprobación explícita.
- El Executor aplica timeout, captura errores y no inicia acciones sin autorización.
- Las acciones con riesgo superior a informativo requieren verificador registrado.
- El Event Log es append-only, local y redacta campos sensibles; no guarda salidas completas.
- La API local ofrece aprobaciones gráficas y eventos de auditoría en vivo por WebSocket.

## Instalación (Windows, PowerShell)

        py -3.12 -m venv .venv
        .venv\Scripts\Activate.ps1
        pip install -e ".[dev]"
        nexo --help

También puedes ejecutar los comandos con `python -m nexo.interfaces.cli`.

## Comandos

- `nexo pending`: tareas académicas próximas. Añade `--approve-github` para consultar issues y PRs.
- `nexo pending --upcoming 3`: muestra tareas con vencimiento en los próximos tres días.
- `nexo add-task "Informe" --subject "Bases de datos" --due 2026-10-15 --approve`.
- `nexo import-tasks data/campusland.csv --approve`: importa un JSON/CSV exportado.
- `nexo run "revisa el repo" --data-class cloud_ok`: planifica con Gemini. Sin `--data-class`, el mensaje se trata como `LOCAL` y no se envía al modelo.
- `nexo github-draft-pr "Resumen" --head feature --base main --approve`: crea un PR draft remoto.
- `nexo github-draft-issue "Investigar error" --approve`: guarda un borrador local, no lo publica.
- `nexo ui`: levanta el panel en `http://localhost:8000`.
- `nexo check-repo`: estado local del workspace.
- `nexo git-diff`: diferencias locales de archivos seguidos.
- `nexo commit-prep --type feat --scope cli --summary "show pending tasks"`.
- `nexo english "I am agree with this idea"`.
- `nexo explain-grammar "present simple"`.
- `nexo mail-pending data/notifications.json`: lee un resumen local.

## Datos y conectores

- Tareas y auditoría se guardan en SQLite dentro de `data/`, fuera de Git.
- Campusland/Moodle se alimenta con `nexo add-task` o `nexo import-tasks`; no automatiza el inicio
    de sesión ni envía entregas. CSV admite cabeceras en inglés/español; JSON admite una lista o un
    objeto con `tasks`.
- El correo se lee desde `.txt`, `.json` o `.eml` local. Adjuntos no se procesan. El sanitizador
    marca automáticamente datos sensibles como `LOCAL` y omite su contenido.
- GitHub consulta issues asignados y PRs abiertos mediante REST API. El token se busca en
    `GITHUB_TOKEN`, `GH_TOKEN` o el keyring del sistema (`nexo` / `github_token`). Consultar requiere
    `--approve-github`; crear un PR draft requiere `--approve`.
- Configura `GEMINI_API_KEY` o `GOOGLE_API_KEY` localmente para `nexo run` y la planificación web.
- Sin clave Gemini, el panel ofrece consultas locales acotadas: estado/cambios de Git, tareas
    académicas próximas y explicaciones de gramática disponibles. Las solicitudes abiertas necesitan
    `GEMINI_API_KEY` o `GOOGLE_API_KEY`; el modo local no escribe archivos ni realiza acciones externas.
- El tutor es offline y revisa reglas comunes A2.4/B1; no sustituye una revisión lingüística
    completa ni comparte el texto con un servicio remoto.

## Seguridad

- `fs.read`, `fs.write`, `fs.list` y correo quedan limitados a rutas dentro del workspace. Las
    escrituras necesitan `--approve` en la CLI o aprobación explícita en el Executor.
- `LOCAL` es la clasificación predeterminada y nunca se envía a Gemini. En `nexo run` se debe
    especificar `--data-class cloud_ok` para compartir la intención; datos `CONFIDENTIAL` también se
    omiten salvo selección explícita. Tokens no forman parte del prompt.
- GitHub y `git.push` son operaciones externas y requieren aprobación. No hay comando CLI de push.
    `git.commit_prep` solo propone un mensaje.
- Todo contenido externo debe tratarse como no confiable y no puede autorizar acciones.
- `.env`, bases de datos y `data/` están ignorados por Git. No guardes tokens en archivos del repo.

## Verificación

        pytest
        ruff check .
        mypy src
