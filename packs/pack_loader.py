from pathlib import Path

import yaml
from pydantic import ValidationError

from packs._schema.pack import IndustryPack

_PACKS_DIR = Path(__file__).parent
_cache: dict[str, IndustryPack] = {}


def load_pack(name: str, *, force_reload: bool = False) -> IndustryPack:
    """Load and validate a pack by name. Results are cached in-process."""
    if name in _cache and not force_reload:
        return _cache[name]

    yaml_path = _PACKS_DIR / name / "pack.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"No pack found at {yaml_path}")

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    try:
        pack = IndustryPack(**raw)
    except ValidationError as exc:
        raise ValueError(f"Pack '{name}' failed schema validation:\n{exc}") from exc

    _cache[name] = pack
    return pack


def clear_cache() -> None:
    _cache.clear()
