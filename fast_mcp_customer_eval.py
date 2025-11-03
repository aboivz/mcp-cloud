# my_server.py
"""
FastMCP server entrypoint (export object `mcp`)
Run with:
    fastmcp run my_server.py:mcp --transport http --port 8000

Tools:
- classify_customer(inputs: dict) -> dict
- score_breakdown(inputs: dict) -> dict

Inputs (JSON dict) expected keys:
  - total_asset_value: float (VND)
  - monthly_salary: float (VND)
  - work_experiences: int (years)
  - age: int (years)
"""
from dataclasses import dataclass
from typing import Dict, Any
from fastmcp import FastMCP

# ----- configuration (tweak nếu cần) -----
ASSET_CAP = 10_000_000_000.0   # 10 tỷ VND
SALARY_CAP = 200_000_000.0    # 200 triệu VND/tháng
EXP_CAP = 40.0                # 40 năm
BASE_SCORE = 500.0
BONUS_POOL = 300.0
WEIGHTS = {"asset": 0.5, "salary": 0.3, "experience": 0.2}
# -------------------------------------------

@dataclass
class CreditInputs:
    total_asset_value: float
    monthly_salary: float
    work_experiences: int
    age: int

mcp = FastMCP("CreditScoringVND")

def _sanitize_and_cast(inputs: Dict[str, Any]) -> CreditInputs:
    """Chuyển và validate các trường từ body JSON."""
    try:
        asset = float(inputs.get("total_asset_value", 0))
        salary = float(inputs.get("monthly_salary", 0))
        exp = int(inputs.get("work_experiences", 0))
        age = int(inputs.get("age", 0))
    except Exception as e:
        raise ValueError(f"Invalid input types: {e}")
    if asset < 0 or salary < 0 or exp < 0 or age < 0:
        raise ValueError("Numeric inputs must be non-negative.")
    return CreditInputs(total_asset_value=asset, monthly_salary=salary,
                        work_experiences=exp, age=age)

def _compute_scores(ci: CreditInputs) -> Dict[str, Any]:
    """Core scoring logic, trả về chi tiết tính toán."""
    asset = max(0.0, float(ci.total_asset_value))
    salary = max(0.0, float(ci.monthly_salary))
    exp = max(0.0, float(ci.work_experiences))
    age = int(max(0, ci.age))

    asset_norm = min(asset / ASSET_CAP, 1.0)
    salary_norm = min(salary / SALARY_CAP, 1.0)
    exp_norm = min(exp / EXP_CAP, 1.0)

    asset_points = BONUS_POOL * WEIGHTS["asset"]
    salary_points = BONUS_POOL * WEIGHTS["salary"]
    exp_points = BONUS_POOL * WEIGHTS["experience"]

    asset_score = asset_norm * asset_points
    salary_score = salary_norm * salary_points
    exp_score = exp_norm * exp_points

    raw_score = BASE_SCORE + asset_score + salary_score + exp_score
    credit_score = int(round(max(BASE_SCORE, min(raw_score, BASE_SCORE + BONUS_POOL))))

    # classification rules
    if credit_score >= 720 and 25 <= age <= 65:
        classification = "high-value"
        reason_class = "Điểm cao và độ tuổi trong ngưỡng ổn định thu nhập/tiêu dùng."
    elif credit_score >= 640 and 21 <= age <= 70:
        classification = "standard"
        reason_class = "Điểm khá và độ tuổi phù hợp, rủi ro trung bình."
    else:
        classification = "risk"
        reason_class = "Điểm thấp hoặc độ tuổi ngoài ngưỡng ưu tiên, rủi ro cao hơn."

    return {
        "credit_score": credit_score,
        "raw_score": raw_score,
        "classification": classification,
        "reason_class": reason_class,
        "components": {
            "asset": {"value": asset, "cap": ASSET_CAP, "norm": round(asset_norm, 6), "points": round(asset_score, 2)},
            "salary": {"value": salary, "cap": SALARY_CAP, "norm": round(salary_norm, 6), "points": round(salary_score, 2)},
            "experience": {"value": exp, "cap": EXP_CAP, "norm": round(exp_norm, 6), "points": round(exp_score, 2)},
        },
        "base": BASE_SCORE,
        "bonus_pool": BONUS_POOL,
        "weights": WEIGHTS
    }

# ----------------- MCP tools -----------------
@mcp.tool
def classify_customer(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trả về {"credit_score", "classification", "reasons": {...}} cho client.
    Nếu có lỗi input sẽ trả object chứa "error".
    """
    try:
        ci = _sanitize_and_cast(inputs)
    except ValueError as e:
        return {"error": "invalid_input", "details": str(e)}

    calc = _compute_scores(ci)
    reasons = {
        "credit_scoring": {
            "base": BASE_SCORE,
            "components": {
                "asset_score": calc["components"]["asset"]["points"],
                "salary_score": calc["components"]["salary"]["points"],
                "experience_score": calc["components"]["experience"]["points"],
            },
            "normalization": {
                "asset_norm": calc["components"]["asset"]["norm"],
                "salary_norm": calc["components"]["salary"]["norm"],
                "experience_norm": calc["components"]["experience"]["norm"],
                "caps": {
                    "asset_cap": ASSET_CAP,
                    "salary_cap": SALARY_CAP,
                    "experience_cap": EXP_CAP,
                },
            },
            "weights": WEIGHTS,
            "explanation": f"Điểm = {BASE_SCORE} + (tài sản {int(WEIGHTS['asset']*100)}% + lương {int(WEIGHTS['salary']*100)}% + kinh nghiệm {int(WEIGHTS['experience']*100)}%) của {BONUS_POOL} điểm bonus."
        },
        "classification": {
            "rule": "high-value nếu score ≥ 720 và 25–65; standard nếu score ≥ 640 và 21–70; else risk.",
            "age": ci.age,
            "reason": calc["reason_class"]
        }
    }

    return {
        "credit_score": calc["credit_score"],
        "classification": calc["classification"],
        "reasons": reasons
    }

@mcp.tool
def score_breakdown(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trả về bản phân tích chi tiết: raw_score, component values, norms, caps, weights.
    Dùng để giải thích/trace.
    """
    try:
        ci = _sanitize_and_cast(inputs)
    except ValueError as e:
        return {"error": "invalid_input", "details": str(e)}

    calc = _compute_scores(ci)
    return {
        "credit_score": calc["credit_score"],
        "raw_score": calc["raw_score"],
        "components": calc["components"],
        "weights": calc["weights"],
        "base": calc["base"],
        "bonus_pool": calc["bonus_pool"]
    }
# -----------------------------------------------

if __name__ == "__main__":
    mcp.run()
