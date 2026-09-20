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
