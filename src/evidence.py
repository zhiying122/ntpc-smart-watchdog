"""
證據鏈與風險知識圖譜（Evidence Chain & Knowledge Graph, R11, R14）
=====================================================================
小小守護員 Smart Watchdog Platform — 可解釋 AI 的可追溯基礎設施。

對應 design.md「Components and Interfaces / 8. Evidence_Chain + Knowledge_Graph」
與「Data Models / EvidenceChain / KnowledgeGraph」，落實需求：

證據鏈（R11，延伸既有 SHAP 特徵歸因）：
  - R11.1：為每一個 AI/風險結論建立證據鏈：結論 → 特徵 → 原始資料 → 官方來源。
  - R11.2：顯示風險結論時，呈現支撐該結論的特徵歸因。
  - R11.3：每一特徵歸因可追溯至其原始資料值。
  - R11.4：每一原始資料值可追溯至其官方來源。
  - R11.5：保留既有 SHAP 特徵歸因作為可解釋輸出。

風險知識圖譜（R14）：
  - R14.1：建立訊號 → 類別 → 風險的節點與關係。
  - R14.2：呈現貢獻某結論的訊號與其所屬類別的關聯。
  - R14.3：每一風險節點皆可追溯至其來源訊號節點。

設計原則（對齊 project-vision 白盒可解釋）：
  - 證據鏈與知識圖譜皆為「規則式／結構化」建構，AI 不參與；SHAP 僅作為特徵
    歸因來源之一，維持可解釋輸出（R11.5）。
  - 「可追溯」是硬性不變式：證據鏈每一環不得有懸空連結（結論須有特徵、特徵須有
    原始值、原始值須有具主管機關的官方來源）；知識圖譜每一風險節點須存在一條
    可經由類別回溯至至少一個來源訊號節點的路徑。
  - 這些不變式由 Property 32（證據鏈完整可追溯）與 Property 33（知識圖譜可回溯）
    以屬性測試驗證。

責任 AI：風險（risk）不等於違法（illegality）。證據鏈只呈現「資料 → 歸因 →
結論」的可追溯關係，不作違法／舞弊斷言。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.models import EvidenceLink, SourceRef


# ==========================================================================
# 輸入資料結構（結論與訊號）
# ==========================================================================
@dataclass
class FeatureAttribution:
    """單一特徵歸因（feature attribution）。

    來源可為既有 SHAP 歸因（Isolation Forest）或規則式指標貢獻（R11.5）。

    - feature      ：特徵／指標名稱（如 "expense_income_ratio"）。
    - raw_value    ：該特徵對應的原始資料值（R11.3）。
    - source       ：原始資料值的官方來源（R11.4）；缺來源時為 None，
                     於建鏈時會被補上「未確認來源」佔位以維持不懸空。
    - contribution ：對結論的貢獻量（SHAP 值或規則權重）；正負代表方向。
    - method       ：歸因方法標記（"shap" / "rule" 等），供可解釋展示。

    Validates: Requirements 11.2, 11.3, 11.4, 11.5
    """
    feature: str
    raw_value: float | str
    source: SourceRef | None = None
    contribution: float = 0.0
    method: str = "rule"


@dataclass
class RiskConclusion:
    """一個待建立證據鏈的風險結論（R11.1）。

    - entity_id     ：機構識別碼。
    - conclusion    ：非空的結論陳述（如「支出結構異常，人事費占比偏高」）。
    - attributions  ：支撐該結論的特徵歸因清單（R11.2）；可含 SHAP 與規則式。

    Validates: Requirements 11.1, 11.2
    """
    entity_id: str
    conclusion: str
    attributions: list[FeatureAttribution] = field(default_factory=list)


@dataclass
class Signal:
    """知識圖譜的來源訊號（R14.1）。

    - signal_id ：訊號唯一識別碼。
    - name      ：訊號名稱（如「113 年支出年增率 +48%」）。
    - category  ：所屬風險類別（財務／裁罰／評鑑／輿情／其他）（R14.1）。
    - weight    ：對風險的貢獻權重（供關係強度呈現）。
    - source    ：官方來源（可為 None）。

    Validates: Requirements 14.1
    """
    signal_id: str
    name: str
    category: str
    weight: float = 0.0
    source: SourceRef | None = None


# ==========================================================================
# 證據鏈（Evidence Chain, R11）
# ==========================================================================
# 當特徵歸因缺官方來源時，補上此佔位來源以維持「原始值 → 來源」不懸空（R11.4）。
UNVERIFIED_SOURCE = SourceRef(dataset="未確認來源", authority="未確認", url=None)


@dataclass
class EvidenceChain:
    """一個風險結論的完整證據鏈（R11.1）。

    結構：結論（conclusion）→ 多條證據環（links: EvidenceLink），每一環串接
    結論 → 特徵歸因 → 原始資料值 → 官方來源，形成可追溯路徑（R11.1–R11.4）。

    不變式（由 Property 32 驗證）：
      - conclusion 非空。
      - 每一 link.feature 非空（特徵歸因存在，R11.2）。
      - 每一 link.raw_value 存在（特徵可追溯至原始值，R11.3）。
      - 每一 link.source 具備主管機關標示（原始值可追溯至官方來源，R11.4），
        無懸空連結。

    Validates: Requirements 11.1, 11.2, 11.3, 11.4
    """
    entity_id: str
    conclusion: str
    links: list[EvidenceLink] = field(default_factory=list)
    # 保留既有 SHAP 特徵歸因作為可解釋輸出（R11.5）：feature -> contribution。
    shap_attribution: dict[str, float] = field(default_factory=dict)

    def is_fully_traceable(self) -> bool:
        """檢查證據鏈是否完整可追溯，無懸空連結（R11.1–R11.4）。

        回傳 True 若且唯若：結論非空、至少一條環，且每一環的
        conclusion / feature / raw_value / source（含主管機關）皆完整。
        """
        if not self.conclusion or not self.links:
            return False
        for link in self.links:
            if not link.conclusion or not link.feature:
                return False
            if link.raw_value is None:
                return False
            if link.source is None or not link.source.authority:
                return False
        return True


def build_evidence_chain(conclusion: RiskConclusion) -> EvidenceChain:
    """由風險結論建立完整可追溯的證據鏈（R11.1–R11.5）。

    對結論的每一個特徵歸因產生一條 EvidenceLink：
      結論 → 特徵（feature）→ 原始資料值（raw_value）→ 官方來源（source）。

    可追溯保證（R11.3, R11.4）：
      - 每一環都帶著結論字串（conclusion），確保由結論可下溯至特徵。
      - 特徵必帶原始值（raw_value）；若歸因未提供則以字串 "N/A" 佔位避免懸空。
      - 原始值必帶官方來源；缺來源時補上 UNVERIFIED_SOURCE（標「未確認」）以
        維持不懸空且誠實標示（不虛構來源，對齊 R16 誠實原則）。

    保留 SHAP（R11.5）：method == "shap" 的歸因會彙整入 shap_attribution，
    作為既有可解釋輸出併同保留。

    參數：
      conclusion：RiskConclusion，含 entity_id、conclusion 字串與特徵歸因清單。

    回傳：
      EvidenceChain，links 與每一特徵歸因一一對應；is_fully_traceable() 為 True
      （當 conclusion 非空且至少一個歸因時）。
    """
    conclusion_text = conclusion.conclusion or ""
    links: list[EvidenceLink] = []
    shap_attribution: dict[str, float] = {}

    for attr in conclusion.attributions:
        # 原始值不得懸空（R11.3）。
        raw_value = attr.raw_value if attr.raw_value is not None else "N/A"
        # 官方來源不得懸空（R11.4）；缺來源以誠實佔位標示。
        source = attr.source if attr.source is not None else UNVERIFIED_SOURCE

        links.append(
            EvidenceLink(
                conclusion=conclusion_text,
                feature=attr.feature,
                raw_value=raw_value,
                source=source,
            )
        )

        # 保留既有 SHAP 特徵歸因作為可解釋輸出（R11.5）。
        if attr.method == "shap":
            shap_attribution[attr.feature] = round(float(attr.contribution), 4)

    return EvidenceChain(
        entity_id=conclusion.entity_id,
        conclusion=conclusion_text,
        links=links,
        shap_attribution=shap_attribution,
    )


# ==========================================================================
# 風險知識圖譜（Knowledge Graph, R14）
# ==========================================================================
# 節點類型常數。
NODE_SIGNAL = "signal"
NODE_CATEGORY = "category"
NODE_RISK = "risk"

# 邊類型常數（有向）：訊號 → 類別、類別 → 風險。
EDGE_SIGNAL_TO_CATEGORY = "signal_to_category"
EDGE_CATEGORY_TO_RISK = "category_to_risk"

# 統一的風險節點識別碼（單一機構的整體風險匯聚節點）。
RISK_NODE_ID = "risk::overall"


@dataclass
class GraphNode:
    """知識圖譜節點（R14.1）。

    - node_id ：節點唯一識別碼。
    - kind    ：節點類型（signal / category / risk）。
    - label   ：顯示標籤。
    - meta    ：附加資訊（如訊號權重、來源等）。

    Validates: Requirements 14.1
    """
    node_id: str
    kind: str
    label: str
    meta: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """知識圖譜有向邊（R14.1, R14.2）。

    - src   ：來源節點 id。
    - dst   ：目標節點 id。
    - kind  ：邊類型（signal_to_category / category_to_risk）。
    - weight：關係強度（來自訊號權重）。

    Validates: Requirements 14.1, 14.2
    """
    src: str
    dst: str
    kind: str
    weight: float = 0.0


@dataclass
class KnowledgeGraph:
    """風險知識圖譜：訊號 → 類別 → 風險（R14）。

    不變式（由 Property 33 驗證）：每一風險節點皆存在一條路徑
    （風險 ← 類別 ← 訊號）回溯至至少一個來源訊號節點（R14.3）。

    Validates: Requirements 14.1, 14.2, 14.3
    """
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    # ---- 查詢輔助 ----
    def nodes_of_kind(self, kind: str) -> list[GraphNode]:
        """回傳指定類型的所有節點。"""
        return [n for n in self.nodes.values() if n.kind == kind]

    def incoming(self, node_id: str) -> list[GraphEdge]:
        """回傳指向指定節點的所有入邊。"""
        return [e for e in self.edges if e.dst == node_id]

    def trace_signals(self, risk_node_id: str) -> list[str]:
        """回溯某風險節點可追溯到的所有來源訊號節點 id（R14.3）。

        路徑：風險節點 ← 類別節點 ← 訊號節點。回傳去重後的訊號 id 清單。
        """
        signal_ids: list[str] = []
        seen: set[str] = set()
        # 風險 ← 類別
        for cat_edge in self.incoming(risk_node_id):
            if cat_edge.kind != EDGE_CATEGORY_TO_RISK:
                continue
            category_id = cat_edge.src
            # 類別 ← 訊號
            for sig_edge in self.incoming(category_id):
                if sig_edge.kind != EDGE_SIGNAL_TO_CATEGORY:
                    continue
                sid = sig_edge.src
                if sid in seen:
                    continue
                node = self.nodes.get(sid)
                if node is not None and node.kind == NODE_SIGNAL:
                    seen.add(sid)
                    signal_ids.append(sid)
        return signal_ids

    def is_fully_traceable(self) -> bool:
        """每一風險節點皆可回溯至至少一個來源訊號節點（R14.3）。"""
        risk_nodes = self.nodes_of_kind(NODE_RISK)
        if not risk_nodes:
            return False
        return all(self.trace_signals(n.node_id) for n in risk_nodes)


def _category_node_id(category: str) -> str:
    """由類別名稱組成穩定的類別節點 id。"""
    return f"category::{category}"


def build_knowledge_graph(
    signals: list[Signal],
    risk_label: str = "整體風險",
) -> KnowledgeGraph:
    """由來源訊號建立風險知識圖譜：訊號 → 類別 → 風險（R14.1–R14.3）。

    建構規則：
      - 每個 Signal 建立一個 signal 節點（R14.1）。
      - 依訊號 category 建立（去重）category 節點，並加入 訊號 → 類別 有向邊
        （R14.1, R14.2）。
      - 建立單一 risk 匯聚節點，並為每個出現過的類別加入 類別 → 風險 有向邊
        （R14.1）。

    可追溯保證（R14.3）：因每條 訊號→類別 與 類別→風險 邊皆成對建立，故每一
    風險節點都能沿 風險 ← 類別 ← 訊號 回溯至其來源訊號；trace_signals() 與
    is_fully_traceable() 可據此驗證（Property 33）。

    參數：
      signals   ：來源訊號清單。
      risk_label：風險節點顯示標籤，預設「整體風險」。

    回傳：
      KnowledgeGraph。當 signals 非空時 is_fully_traceable() 為 True；
      signals 為空時回傳僅含風險節點但無法回溯的空圖（is_fully_traceable()==False）。
    """
    graph = KnowledgeGraph()

    # 風險匯聚節點（R14.1）。
    graph.nodes[RISK_NODE_ID] = GraphNode(
        node_id=RISK_NODE_ID,
        kind=NODE_RISK,
        label=risk_label,
    )

    linked_categories: set[str] = set()

    for sig in signals:
        # 1) 訊號節點（R14.1）。
        graph.nodes[sig.signal_id] = GraphNode(
            node_id=sig.signal_id,
            kind=NODE_SIGNAL,
            label=sig.name,
            meta={
                "category": sig.category,
                "weight": sig.weight,
                "source": sig.source,
            },
        )

        # 2) 類別節點（去重）（R14.1）。
        cat_id = _category_node_id(sig.category)
        if cat_id not in graph.nodes:
            graph.nodes[cat_id] = GraphNode(
                node_id=cat_id,
                kind=NODE_CATEGORY,
                label=sig.category,
            )

        # 3) 訊號 → 類別 邊（R14.1, R14.2）。
        graph.edges.append(
            GraphEdge(
                src=sig.signal_id,
                dst=cat_id,
                kind=EDGE_SIGNAL_TO_CATEGORY,
                weight=sig.weight,
            )
        )

        # 4) 類別 → 風險 邊（每類別一條，去重）（R14.1）。
        if sig.category not in linked_categories:
            linked_categories.add(sig.category)
            graph.edges.append(
                GraphEdge(
                    src=cat_id,
                    dst=RISK_NODE_ID,
                    kind=EDGE_CATEGORY_TO_RISK,
                    weight=sig.weight,
                )
            )

    return graph
