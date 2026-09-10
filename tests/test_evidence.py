"""
證據鏈與知識圖譜單元測試（Evidence Chain & Knowledge Graph Unit Tests）
==========================================================================
對應 Task 8.1（src/evidence.py），驗證 build_evidence_chain /
build_knowledge_graph 的具體行為與可追溯不變式（R11.1–R11.5, R14.1–R14.3）。

註：Property 32（證據鏈完整可追溯）與 Property 33（知識圖譜可回溯）之屬性測試
屬於獨立的選用任務 8.2 / 8.3；本檔僅涵蓋具體範例與邊界之單元測試。
"""
from datetime import date

from src.evidence import (
    EDGE_CATEGORY_TO_RISK,
    EDGE_SIGNAL_TO_CATEGORY,
    NODE_CATEGORY,
    NODE_RISK,
    NODE_SIGNAL,
    RISK_NODE_ID,
    UNVERIFIED_SOURCE,
    EvidenceChain,
    FeatureAttribution,
    KnowledgeGraph,
    RiskConclusion,
    Signal,
    build_evidence_chain,
    build_knowledge_graph,
)
from src.models import EvidenceLink, SourceRef


def _src(name="財政決算資料集"):
    return SourceRef(dataset=name, authority="新北市教育局",
                     url="https://example.gov.tw", last_updated=date(2024, 1, 1))


# --------------------------------------------------------------------------
# build_evidence_chain（R11.1–R11.5）
# --------------------------------------------------------------------------
def test_evidence_chain_links_conclusion_feature_value_source():
    """每一環串接 結論 → 特徵 → 原始值 → 官方來源（R11.1–R11.4）。"""
    concl = RiskConclusion(
        entity_id="P001",
        conclusion="支出結構異常，人事費占比偏高",
        attributions=[
            FeatureAttribution(feature="personnel_ratio", raw_value=0.82,
                               source=_src(), contribution=0.31, method="rule"),
            FeatureAttribution(feature="expense_yoy_pct", raw_value=0.48,
                               source=_src(), contribution=0.22, method="shap"),
        ],
    )
    chain = build_evidence_chain(concl)

    assert isinstance(chain, EvidenceChain)
    assert chain.entity_id == "P001"
    assert chain.conclusion == "支出結構異常，人事費占比偏高"
    assert len(chain.links) == 2
    for link in chain.links:
        assert isinstance(link, EvidenceLink)
        assert link.conclusion == chain.conclusion   # 由結論可下溯（R11.1）
        assert link.feature                            # 特徵歸因存在（R11.2）
        assert link.raw_value is not None              # 可追溯至原始值（R11.3）
        assert link.source.authority                   # 可追溯至官方來源（R11.4）
    assert chain.is_fully_traceable() is True


def test_evidence_chain_preserves_shap_attribution():
    """method=='shap' 的歸因保留為 SHAP 可解釋輸出（R11.5）。"""
    concl = RiskConclusion(
        entity_id="P002",
        conclusion="多維財務異常",
        attributions=[
            FeatureAttribution(feature="benford_mad", raw_value=0.021,
                               source=_src(), contribution=0.4123, method="shap"),
            FeatureAttribution(feature="beneish_score", raw_value=-1.2,
                               source=_src(), contribution=0.15, method="rule"),
        ],
    )
    chain = build_evidence_chain(concl)
    # 只有 shap 方法進入 shap_attribution
    assert chain.shap_attribution == {"benford_mad": 0.4123}


def test_evidence_chain_missing_source_uses_unverified_placeholder():
    """缺官方來源時補上「未確認」佔位以維持不懸空且誠實標示（R11.4, R16）。"""
    concl = RiskConclusion(
        entity_id="P003",
        conclusion="收入年增率異常",
        attributions=[
            FeatureAttribution(feature="income_yoy_pct", raw_value=1.5, source=None),
        ],
    )
    chain = build_evidence_chain(concl)
    assert chain.links[0].source is UNVERIFIED_SOURCE
    assert chain.links[0].source.authority == "未確認"
    # 佔位仍具備 authority，故仍視為可追溯（不懸空）
    assert chain.is_fully_traceable() is True


def test_evidence_chain_missing_raw_value_uses_placeholder():
    """歸因缺原始值時以 'N/A' 佔位避免懸空（R11.3）。"""
    concl = RiskConclusion(
        entity_id="P004",
        conclusion="資料缺漏",
        attributions=[FeatureAttribution(feature="tuition_actual",
                                         raw_value=None, source=_src())],
    )
    chain = build_evidence_chain(concl)
    assert chain.links[0].raw_value == "N/A"
    assert chain.is_fully_traceable() is True


def test_evidence_chain_empty_conclusion_not_traceable():
    """結論為空或無歸因時不視為完整可追溯。"""
    empty = build_evidence_chain(RiskConclusion(entity_id="P005", conclusion=""))
    assert empty.is_fully_traceable() is False

    no_attr = build_evidence_chain(RiskConclusion(entity_id="P006", conclusion="結論"))
    assert no_attr.is_fully_traceable() is False


# --------------------------------------------------------------------------
# build_knowledge_graph（R14.1–R14.3）
# --------------------------------------------------------------------------
def _signals():
    return [
        Signal(signal_id="s1", name="人事費占比偏高", category="財務", weight=0.4, source=_src()),
        Signal(signal_id="s2", name="支出年增率突變", category="財務", weight=0.3),
        Signal(signal_id="s3", name="112 年裁罰紀錄", category="裁罰", weight=0.5),
    ]


def test_knowledge_graph_builds_signal_category_risk_nodes():
    """建立 訊號 → 類別 → 風險 的節點與關係（R14.1）。"""
    graph = build_knowledge_graph(_signals())
    assert isinstance(graph, KnowledgeGraph)

    signals = graph.nodes_of_kind(NODE_SIGNAL)
    categories = graph.nodes_of_kind(NODE_CATEGORY)
    risks = graph.nodes_of_kind(NODE_RISK)

    assert {n.node_id for n in signals} == {"s1", "s2", "s3"}
    # 財務、裁罰 兩類（去重）
    assert {n.label for n in categories} == {"財務", "裁罰"}
    assert len(risks) == 1
    assert risks[0].node_id == RISK_NODE_ID


def test_knowledge_graph_edges_signal_to_category_to_risk():
    """邊分為 訊號→類別 與 類別→風險 兩類，方向正確（R14.1, R14.2）。"""
    graph = build_knowledge_graph(_signals())
    s2c = [e for e in graph.edges if e.kind == EDGE_SIGNAL_TO_CATEGORY]
    c2r = [e for e in graph.edges if e.kind == EDGE_CATEGORY_TO_RISK]

    # 3 條 訊號→類別
    assert len(s2c) == 3
    # 2 條 類別→風險（財務、裁罰各一，去重）
    assert len(c2r) == 2
    assert all(e.dst == RISK_NODE_ID for e in c2r)


def test_knowledge_graph_risk_traces_back_to_signals():
    """每一風險節點可回溯至來源訊號節點（R14.3）。"""
    graph = build_knowledge_graph(_signals())
    traced = graph.trace_signals(RISK_NODE_ID)
    assert set(traced) == {"s1", "s2", "s3"}
    assert graph.is_fully_traceable() is True


def test_knowledge_graph_single_category_dedup():
    """同類別多訊號時類別節點與 類別→風險 邊皆去重（R14.1）。"""
    signals = [
        Signal(signal_id="a", name="訊號A", category="財務", weight=0.1),
        Signal(signal_id="b", name="訊號B", category="財務", weight=0.2),
    ]
    graph = build_knowledge_graph(signals)
    assert len(graph.nodes_of_kind(NODE_CATEGORY)) == 1
    c2r = [e for e in graph.edges if e.kind == EDGE_CATEGORY_TO_RISK]
    assert len(c2r) == 1
    assert set(graph.trace_signals(RISK_NODE_ID)) == {"a", "b"}


def test_knowledge_graph_empty_signals_not_traceable():
    """無訊號時風險節點無來源可回溯，非完整可追溯。"""
    graph = build_knowledge_graph([])
    assert graph.nodes_of_kind(NODE_RISK)
    assert graph.trace_signals(RISK_NODE_ID) == []
    assert graph.is_fully_traceable() is False
