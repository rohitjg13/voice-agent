"""Seed pack_templates from packs/*/pack.yaml (read-only templates for tenants).

Usage: python -m infra.seed_templates
"""

import asyncio
import json
from pathlib import Path

from orchestrator import db
from packs.pack_loader import load_pack

_PACKS_DIR = Path(__file__).parent.parent / "packs"


async def main() -> None:
    names = sorted(p.parent.name for p in _PACKS_DIR.glob("*/pack.yaml"))
    conn = await db.connect_direct()
    try:
        for name in names:
            pack = load_pack(name)
            await conn.execute(
                """
                INSERT INTO pack_templates (name, version, config)
                VALUES ($1, $2, $3)
                ON CONFLICT (name) DO UPDATE
                SET version = EXCLUDED.version,
                    config = EXCLUDED.config,
                    updated_at = NOW()
                """,
                name,
                pack.version,
                json.dumps(pack.model_dump()),
            )
            print(f"seeded {name} v{pack.version}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
