from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response

import database


def _resolve_skill_path(skill_name: Optional[str] = None):
    root = Path(__file__).parent.parent.parent
    candidates = []
    if skill_name:
        candidates.extend([
            root / 'skills' / skill_name / 'SKILL.md',
            root / 'skills' / skill_name / 'skill.md',
        ])
    else:
        candidates.extend([
            root / 'skills' / 'sooppiy' / 'SKILL.md',
            root / 'skills' / 'sooppiy' / 'skill.md',
        ])

    for path in candidates:
        if path.exists():
            return path
    return None


def register_misc_routes(app: FastAPI) -> None:
    @app.get('/skill.md')
    @app.get('/SKILL.md')
    async def get_skill_index():
        skill_path = _resolve_skill_path()
        if skill_path is None:
            return {'error': 'main skill doc not found'}
        return Response(content=skill_path.read_text(encoding='utf-8'), media_type='text/markdown')

    @app.get('/skill/{skill_name}')
    async def get_skill_page(skill_name: str):
        skill_path = _resolve_skill_path(skill_name)
        if skill_path is not None:
            return Response(content=skill_path.read_text(encoding='utf-8'), media_type='text/markdown')
        return {'error': f"Skill '{skill_name}' not found"}

    @app.get('/skill/{skill_name}/raw')
    async def get_skill_raw(skill_name: str):
        skill_path = _resolve_skill_path(skill_name)
        if skill_path is not None:
            return skill_path.read_text(encoding='utf-8')
        return {'error': f"Skill '{skill_name}' not found"}

    @app.get('/')
    async def serve_index():
        index_path = Path(__file__).parent.parent / 'frontend' / 'dist' / 'index.html'
        if index_path.exists():
            return FileResponse(index_path)
        return {'message': 'Sooppiy API'}

    @app.get('/assets/{file}')
    async def serve_assets(file: str):
        asset_path = Path(__file__).parent.parent / 'frontend' / 'dist' / 'assets' / file
        if asset_path.exists():
            return FileResponse(asset_path)
        return Response(status_code=404)

    @app.get('/api/health')
    async def health():
        """Liveness probe. Returns JSON only — never the SPA.

        Deliberately reports no database identifiers: this endpoint is public.
        """
        try:
            conn = database.get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT 1')
                cursor.fetchone()
            finally:
                conn.close()
        except Exception:
            return JSONResponse({'status': 'degraded', 'database': 'error'}, status_code=503)
        return {'status': 'ok', 'database': 'ok'}

    @app.get('/{path:path}')
    async def serve_spa_fallback(path: str):
        # An unmatched /api/* path must NOT fall through to index.html: a 200 +
        # HTML response makes a dead backend indistinguishable from a healthy
        # one for any status-code-based monitor.
        if path == 'api' or path.startswith('api/'):
            return JSONResponse({'detail': 'Not Found'}, status_code=404)
        index_path = Path(__file__).parent.parent / 'frontend' / 'dist' / 'index.html'
        if index_path.exists():
            return FileResponse(index_path)
        return {'message': 'Sooppiy API'}
