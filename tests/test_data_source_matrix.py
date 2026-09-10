"""
資料來源矩陣單元測試（Data_Source_Matrix, R16）
==================================================
驗證 src/data_source_matrix.py：
  - 每一資料源記錄 R16.1 要求的完整屬性（來源/資料集/主管機關/更新頻率/
    格式/關鍵欄位/可信度/是否有 API/是否可下載/是否可追溯/用途/風險）。
  - 僅列入實際存在或已確認的資料集（R16.2）。
  - 尚未確認可用性者誠實標示為「未確認」而不宣稱可用（R16.3）。
  - 不虛構任何資料集（R16.4）——不列入實際不存在的資料集。

對應 Task 15.1「實作資料來源矩陣」（Requirements 16.1, 16.2, 16.3, 16.4）。
本表以單次設定完整性檢查（smoke / 單元測試）驗收，非屬性測試
（見 design.md「Smoke / 設定與文件檢查」）。
"""
import pytest

from src.data_source_matrix import (
    DATA_SOURCE_MATRIX,
    UNCONFIRMED_LABEL,
    Availability,
    DataSourceEntry,
    confirmed_sources,
    find_by_dataset,
    get_matrix,
    unconfirmed_sources,
)


# --------------------------------------------------------------------------
# 實際存在／已確認的資料集（R16.2）
# --------------------------------------------------------------------------
# 依 .kiro/steering/project-vision.md 與實際檔案盤點，以下為確認存在的資料集。
CONFIRMED_DATASET_KEYWORDS = (
    "決算書",          # 公校決算書 112/113/114（有文字層）
    "非營利幼兒園財報",  # 非營利園財報 110~113（掃描影像，檔案存在）
)


def test_matrix_is_non_empty_static_table():
    """矩陣為非空的靜態設定表（R16.1）。"""
    assert len(get_matrix()) > 0
    assert get_matrix() is DATA_SOURCE_MATRIX


def test_every_entry_records_all_required_attributes():
    """每一資料源皆記錄 R16.1 要求的十二項屬性且非空。"""
    for e in DATA_SOURCE_MATRIX:
        for attr in DataSourceEntry.REQUIRED_ATTRIBUTES:
            assert hasattr(e, attr), f"缺少屬性 {attr}：{e.dataset}"
            value = getattr(e, attr)
            # 三態能力旗標為列舉；其餘字串/欄位需非空。
            if isinstance(value, Availability):
                continue
            if attr == "key_fields":
                assert len(value) > 0, f"key_fields 不可為空：{e.dataset}"
            else:
                assert isinstance(value, str) and value.strip(), (
                    f"屬性 {attr} 不可為空：{e.dataset}"
                )


def test_entries_are_immutable():
    """條目為 frozen（靜態設定表建立後不可竄改）。"""
    entry = DATA_SOURCE_MATRIX[0]
    with pytest.raises(Exception):
        entry.dataset = "竄改"  # type: ignore[misc]


def test_confirmed_datasets_present():
    """確認存在的核心資料集（公校決算書、非營利園財報）確實列入（R16.2）。"""
    all_datasets = " | ".join(e.dataset for e in DATA_SOURCE_MATRIX)
    for keyword in CONFIRMED_DATASET_KEYWORDS:
        assert keyword in all_datasets, f"應列入已確認資料集：{keyword}"


def test_confirmed_sources_marked_confirmed():
    """公校決算書為已確認可用（CONFIRMED）。"""
    gongxiao = find_by_dataset(
        "公校（含市立幼兒園）決算書 112/113/114 年度"
    )
    assert gongxiao is not None
    assert gongxiao.availability == Availability.CONFIRMED
    assert not gongxiao.is_unconfirmed()


def test_unconfirmed_sources_labeled_unconfirmed():
    """尚未確認的官方資料源（裁罰/評鑑/收費）誠實標示為「未確認」（R16.3）。"""
    unconfirmed = unconfirmed_sources()
    assert len(unconfirmed) > 0
    for e in unconfirmed:
        assert e.availability == Availability.UNCONFIRMED
        assert e.availability.value == UNCONFIRMED_LABEL == "未確認"


def test_unconfirmed_sources_do_not_claim_available():
    """未確認資料源不得宣稱可用：其能力旗標不得標為已確認的下載/API（R16.3）。"""
    for e in unconfirmed_sources():
        # 未確認整體可用性者，不應宣稱其官方 API 或下載為已確認。
        assert e.has_api != Availability.CONFIRMED
        assert e.downloadable != Availability.CONFIRMED


def test_official_penalty_source_is_unconfirmed():
    """官方全量裁罰資料源之可用性標為未確認（僅持有示範樣本，R16.3）。"""
    penalty = find_by_dataset("裁罰紀錄（官方全量）")
    assert penalty is not None
    assert penalty.is_unconfirmed()
    # 誠實說明目前僅有示範樣本，非官方全量資料。
    assert "樣本" in penalty.notes


def test_confirmed_and_unconfirmed_partition_matrix():
    """已確認與未確認兩集合互斥且涵蓋整個矩陣（無第三態遺漏）。"""
    confirmed = confirmed_sources()
    unconfirmed = unconfirmed_sources()
    assert len(confirmed) + len(unconfirmed) == len(DATA_SOURCE_MATRIX)
    confirmed_ids = {id(e) for e in confirmed}
    unconfirmed_ids = {id(e) for e in unconfirmed}
    assert confirmed_ids.isdisjoint(unconfirmed_ids)


def test_no_fabricated_dataset_lookup_returns_none():
    """查詢不存在的資料集回傳 None，不虛構條目（R16.4）。"""
    assert find_by_dataset("不存在的虛構資料集XYZ") is None


def test_dataset_names_are_unique():
    """資料集名稱不重複（避免同一資料被虛構為多筆，R16.4）。"""
    names = [e.dataset for e in DATA_SOURCE_MATRIX]
    assert len(names) == len(set(names))


def test_all_entries_have_authority_for_traceability():
    """每一資料源皆標註主管機關以利追溯（R16.1）。"""
    for e in DATA_SOURCE_MATRIX:
        assert e.authority.strip(), f"缺主管機關：{e.dataset}"
