"""
幼兒園基礎評鑑輪替制度對照（Evaluation Cycle Reference）— 純邏輯
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網的評鑑狀態判定。

領域知識（重要）：
--------------------------------------------------------------------------
新北市幼兒園「基礎評鑑」採 **三年一週期、分年分區輪替訪視**——每一學年度只
訪視特定幾個行政區。因此某園「沒有評鑑結果」往往不是資料缺漏或抓取失敗，
而是「該園所屬行政區尚未排入本輪評鑑」（制度設計）。

本模組據此把「無評鑑等第」的原始空值（nan）轉為官方用語的正式狀態：
  - 已接受評鑑：顯示評鑑等第。
  - 尚未接受評鑑：說明係採分年分區輪替，該區尚未排入本輪。

資料來源：全國教保資訊網評鑑結果查詢（ap.ece.moe.edu.tw/webecems/evaSearch.aspx）、
新北市幼兒教育資源網基礎評鑑結果查詢（kidedu.ntpc.edu.tw）。輪替年區清單為
本專案依公開資訊整理，實務上應以主管機關當年度公告為準。
"""
from __future__ import annotations

#: 各學年度受評行政區（依公開資訊整理；實際以主管機關公告為準）。
#: key 為學年度（民國學年），value 為該學年度排入受評的行政區集合。
EVAL_SCHEDULE: dict[int, frozenset[str]] = {
    114: frozenset({"三重區", "蘆洲區", "三峽區", "樹林區"}),
    115: frozenset({
        "汐止區", "新店區", "烏來區", "石碇區", "深坑區", "坪林區",
        "瑞芳區", "平溪區", "雙溪區", "貢寮區", "鶯歌區",
    }),
}

#: 目前展示所採的「本輪」學年度（供說明文字引用）。
CURRENT_SCHOOL_YEAR = 115

#: 官方狀態用語。
STATUS_EVALUATED = "已接受評鑑"
STATUS_PENDING = "尚未接受評鑑"


def scheduled_year_for(district: str) -> int | None:
    """回傳某行政區被排入受評的學年度；未在已知排程中回 None。"""
    d = (district or "").strip()
    if not d:
        return None
    for year, districts in EVAL_SCHEDULE.items():
        if d in districts:
            return year
    return None


def evaluation_status(district: str, grade: object) -> tuple[str, str]:
    """判定某園的評鑑狀態與說明文字：(狀態用語, 家長友善說明)。

    規則：
      1. 有評鑑等第（grade 非空）→ 已接受評鑑，說明附等第。
      2. 無等第，但所屬行政區在已知排程 → 尚未接受評鑑（點出排入的學年度）。
      3. 無等第且行政區不在已知排程 → 尚未接受評鑑（說明採分年分區輪替，
         該區尚未排入本輪，非資料缺漏）。

    回傳的說明一律為官方用語導向、不含機構優劣評價。
    """
    g = "" if grade is None else str(grade).strip()
    if g and g.lower() != "nan":
        return STATUS_EVALUATED, f"{g} 等（基礎評鑑通過）"

    year = scheduled_year_for(district)
    if year is not None:
        return STATUS_PENDING, (
            f"尚未接受評鑑（本市評鑑採分年分區輪替訪視，"
            f"{district}排入 {year} 學年度受評，結果公告後將更新）"
        )
    return STATUS_PENDING, (
        "尚未接受評鑑（本市評鑑採分年分區輪替訪視，"
        "該園所屬行政區尚未排入本輪評鑑；此為制度設計，非該園之缺漏）"
    )
