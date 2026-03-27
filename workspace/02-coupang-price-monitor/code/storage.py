# code/storage.py
"""
JSON 파일 기반 상품 목록 영속성 관리 (CRUD)
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

DATA_FILE = Path("data/products.json")


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"products": {}}
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_product(url: str, target_price: float, name: str = "") -> dict:
    data = _load()
    product_id = str(uuid.uuid4())
    product = {
        "id": product_id,
        "url": url,
        "name": name,
        "target_price": target_price,
        "current_price": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    data["products"][product_id] = product
    _save(data)
    return product


def get_product(product_id: str) -> Optional[dict]:
    data = _load()
    return data["products"].get(product_id)


def list_products() -> list[dict]:
    data = _load()
    return list(data["products"].values())


def update_product(product_id: str, **kwargs) -> Optional[dict]:
    data = _load()
    product = data["products"].get(product_id)
    if product is None:
        return None
    ALLOWED = {"name", "url", "target_price", "current_price"}
    for key, value in kwargs.items():
        if key in ALLOWED:
            product[key] = value
    product["updated_at"] = datetime.now().isoformat()
    data["products"][product_id] = product
    _save(data)
    return product


def delete_product(product_id: str) -> bool:
    data = _load()
    if product_id not in data["products"]:
        return False
    del data["products"][product_id]
    _save(data)
    return True