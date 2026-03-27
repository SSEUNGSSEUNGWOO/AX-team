```python
# SpotMind Backend - main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import json
import math
import random
from datetime import datetime

app = FastAPI(title="SpotMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory store (MVP) ──────────────────────────────────────────────────────
ANALYSIS_STORE: dict = {}
CRITERIA_STORE: dict = {
    "default": {
        "min_population": 10000,
        "min_float_population": 5000,
        "max_competitor_count": 3,
        "min_avg_sales": 50000000,
        "weight_population": 0.3,
        "weight_sales": 0.3,
        "weight_competitor": 0.2,
        "weight_infra": 0.2,
    }
}

# ── Schema ─────────────────────────────────────────────────────────────────────
class LocationRequest(BaseModel):
    address: str
    lat: float
    lng: float
    brand_id: Optional[str] = "default"
    radius_m: Optional[int] = 500

class CriteriaUpdate(BaseModel):
    brand_id: str
    min_population: Optional[int] = None
    min_float_population: Optional[int] = None
    max_competitor_count: Optional[int] = None
    min_avg_sales: Optional[int] = None
    weight_population: Optional[float] = None
    weight_sales: Optional[float] = None
    weight_competitor: Optional[float] = None
    weight_infra: Optional[float] = None

class AnalysisResult(BaseModel):
    analysis_id: str
    address: str
    lat: float
    lng: float
    score: float
    grade: str
    recommendation: str
    detail: dict
    created_at: str

# ── Helpers ────────────────────────────────────────────────────────────────────
def _grade(score: float) -> str:
    if score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "D"

def _recommendation(grade: str) -> str:
    mapping = {
        "A": "출점 강력 권고 — 핵심 상권 요건 충족",
        "B": "출점 권고 — 보조 지표 보완 후 진행 권장",
        "C": "조건부 검토 — 추가 현장 실사 필요",
        "D": "출점 비권고 — 핵심 요건 미달",
    }
    return mapping.get(grade, "분석 불가")

def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _mock_market_data(lat: float, lng: float, radius_m: int) -> dict:
    """
    실제 환경: 공공데이터포털 상권 API / KT BigData / NICE 지수 연동
    MVP: 시드 기반 결정론적 모의 데이터
    """
    seed = int((lat * 1000 + lng * 1000)) % 9999
    rng = random.Random(seed)
    return {
        "population_1km": rng.randint(8000, 60000),
        "float_population_daily": rng.randint(2000, 30000),
        "competitor_count": rng.randint(0, 8),
        "avg_monthly_sales_krw": rng.randint(20000000, 150000000),
        "subway_within_500m": rng.choice([True, False]),
        "bus_stop_count": rng.randint(0, 6),
        "office_building_count": rng.randint(0, 20),
        "residential_household": rng.randint(500, 8000),
    }

def _score_location(market: dict, criteria: dict) -> dict:
    # 인구 점수 (0~100)
    pop_score = min(market["population_1km"] / criteria["min_population"] * 60, 100)

    # 유동인구 점수
    float_score = min(
        market["float_population_daily"] / criteria["min_float_population"] * 60, 100
    )
    population_combined = (pop_score * 0.5 + float_score * 0.5)

    # 매출 점수
    sales_score = min(
        market["avg_monthly_sales_krw"] / criteria["min_avg_sales"] * 60, 100
    )

    # 경쟁 점수 (경쟁자 적을수록 고점)
    raw_comp = max(0, criteria["max_competitor_count"] - market["competitor_count"])
    comp_score = min(raw_comp / max(criteria["max_competitor_count"], 1) * 100, 100)

    # 인프라 점수
    infra_base = 0
    if market["subway_within_500m"]:
        infra_base += 50
    infra_base += min(market["bus_stop_count"] * 8, 30)
    infra_base += min(market["office_building_count"] * 1.5, 20)
    infra_score = min(infra_base, 100)

    # 가중 합산
    w = criteria
    total = (
        population_combined * w["weight_population"]
        + sales_score * w["weight_sales"]
        + comp_score * w["weight_competitor"]
        + infra_score * w["weight_infra"]
    )

    return {
        "total_score": round(total, 2),
        "breakdown": {
            "population_score": round(population_combined, 2),
            "sales_score": round(sales_score, 2),
            "competitor_score": round(comp_score, 2),
            "infra_score": round(infra_score, 2),
        },
    }

def _generate_analysis_id() -> str:
    return f"ANL-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "SpotMind", "ts": datetime.utcnow().isoformat()}

@app.post("/api/v1/analyze", response_model=AnalysisResult)
def analyze_location(req: LocationRequest):
    criteria_key = req.brand_id if req.brand_id in CRITERIA_STORE else
"default"
    criteria = CRITERIA_STORE[criteria_key]
    score_data = _calc_scores(req, criteria)
    result = AnalysisResult(
        analysis_id=_generate_analysis_id(),
        brand_id=req.brand_id or "default",
        location=req.location,
        recommendation=score_data["recommendation"],
        total_score=score_data["total_score"],
        sub_scores=score_data["sub_scores"],
        created_at=datetime.utcnow(),
    )
    ANALYSIS_STORE[result.analysis_id] = result
    return result

@app.get("/api/v1/analyze/{analysis_id}", response_model=AnalysisResult)
def get_analysis(analysis_id: str):
    result = ANALYSIS_STORE.get(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result

@app.get("/api/v1/criteria/{brand_id}")
def get_criteria(brand_id: str):
    if brand_id not in CRITERIA_STORE:
        raise HTTPException(status_code=404, detail="Brand criteria not found")
    return CRITERIA_STORE[brand_id]