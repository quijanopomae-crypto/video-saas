# Desarrollo local

Esta infraestructura es deliberadamente mínima. El objetivo es programar el SaaS sin convertir el PC del propietario en infraestructura de producción.

## Requisitos

- Git
- Python 3.12+
- Node.js 24+
- Docker Desktop
- FFmpeg para el smoke local de render (el CI lo instala explícitamente)

## Windows / PowerShell

1. Clona el repositorio.
2. Ejecuta `Copy-Item .env.example .env`.
3. Ejecuta `.\scripts\dev.ps1`.
4. API: `http://127.0.0.1:8000/health`.
5. Web: `http://127.0.0.1:3000`.
6. Para validar todo: `.\scripts\test.ps1`.

`dev.ps1` levanta PostgreSQL con Docker y abre API y Web en procesos separados.

## Componentes

- `apps/api`: FastAPI, PostgreSQL/Alembic, adapters locales y worker FFmpeg.
- `apps/web`: Next.js/TypeScript y proxy interno hacia la API.
- `docker-compose.yml`: PostgreSQL solamente.
- `Product CI`: backend, frontend y smoke end-to-end.

Los adapters de storage, queue y workflow son fakes en memoria. R2, Queues y Workflows reales se conectarán en una tarea posterior. No se almacenan credenciales en Git.

## Seguridad

`.env` está ignorado. `.env.example` solo contiene valores locales no secretos. Provider Preflight y requests pagados permanecen deshabilitados en esta fase.

## Autenticación local

La persistencia multiusuario ya no confía en un `owner_id` enviado por el cliente como identidad. Los endpoints `/owners/{owner_id}/...` requieren un Bearer JWT válido y el `owner_id` de la ruta debe coincidir con el `user_id` autenticado.

Para desarrollo local define `AUTH_JWT_SECRET` en `.env` con un valor aleatorio de al menos 32 caracteres. El ejemplo versionado lo deja vacío deliberadamente. Las contraseñas se almacenan con hash Argon2 mediante `pwdlib`; los tokens no se persisten en PostgreSQL.

El comportamiento actual de `project_id` sigue siendo determinista: la misma solicitud canónica del mismo owner produce el mismo `project_id` y el POST persistente actúa de forma idempotente (upsert). Cambiar a “un proyecto nuevo por cada click” es una decisión de producto OWNER-ONLY y no se cambia silenciosamente durante esta remediación.
