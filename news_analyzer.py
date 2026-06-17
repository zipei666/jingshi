from __future__ import annotations

from dataclasses import dataclass, field

from models import FlashNewsItem


LEVEL_SCORE = {"S": 4, "A": 3, "B": 2, "C": 1}


@dataclass(slots=True)
class Rule:
    name: str
    keywords: tuple[str, ...]
    level: str
    markets: tuple[str, ...]
    direction: str
    reason: str


@dataclass(slots=True)
class NewsAnalysis:
    level: str = "C"
    markets: list[str] = field(default_factory=list)
    direction: str = "不确定"
    reason: str = "暂无明显高影响信号。"
    rule_hits: list[str] = field(default_factory=list)


RULES: tuple[Rule, ...] = (
    Rule("美国CPI/通胀", ("cpi", "消费者物价", "通胀", "核心通胀"), "S", ("黄金", "美元", "美股", "债券"), "不确定", "美国通胀数据通常会影响降息预期、美元和实际利率。"),
    Rule("美国非农", ("非农", "失业率", "就业人数", "adp"), "S", ("黄金", "美元", "美股", "债券"), "不确定", "就业数据会影响美联储政策预期和风险资产定价。"),
    Rule("美联储利率", ("美联储", "降息", "加息", "利率决议", "鲍威尔", "fomc"), "S", ("黄金", "美元", "美股", "债券", "外汇"), "不确定", "美联储政策信号会直接影响美元、利率和主要资产风险偏好。"),
    Rule("OPEC/原油供给", ("opec", "欧佩克", "减产", "增产", "原油产量"), "A", ("原油",), "不确定", "产油国供给变化会影响原油供需预期。"),
    Rule("EIA/API库存", ("eia", "api", "原油库存", "汽油库存", "库欣"), "A", ("原油",), "不确定", "库存变化会影响短线原油供需判断。"),
    Rule("地缘冲突", ("袭击", "战争", "冲突", "导弹", "停火", "红海", "中东", "乌克兰", "俄罗斯", "以色列", "伊朗"), "A", ("黄金", "原油", "美元", "美股"), "不确定", "地缘风险可能推升避险资产，并影响能源供给风险溢价。"),
    Rule("制裁/贸易限制", ("制裁", "关税", "出口管制", "禁令", "贸易限制"), "A", ("美元", "美股", "A股", "港股"), "不确定", "政策限制会影响相关行业风险偏好和跨境贸易预期。"),
    Rule("中国央行/政策", ("央行", "降准", "mlf", "lpr", "逆回购", "中国人民银行"), "A", ("A股", "港股", "债券", "外汇"), "不确定", "流动性和利率政策会影响人民币资产和市场风险偏好。"),
    Rule("加密货币", ("比特币", "以太坊", "btc", "eth", "加密货币", "现货etf"), "B", ("加密货币",), "不确定", "加密资产相关消息会影响币价和风险偏好。"),
    Rule("股市财报/指引", ("财报", "业绩", "营收", "利润", "指引", "回购"), "B", ("美股", "A股", "港股"), "不确定", "公司业绩和指引会影响权益市场情绪。"),
)


POSITIVE_TERMS = ("降息", "宽松", "减产", "库存下降", "低于预期", "停火", "刺激", "回购", "上调")
NEGATIVE_TERMS = ("加息", "紧缩", "增产", "库存增加", "高于预期", "袭击", "制裁", "下调", "衰退")


class NewsAnalyzer:
    def __init__(self, logger) -> None:
        self.logger = logger

    def analyze(self, item: FlashNewsItem) -> NewsAnalysis:
        return self._analyze_rules(item.content)

    def apply_to_item(self, item: FlashNewsItem) -> None:
        analysis = self.analyze(item)
        item.analysis_level = analysis.level
        item.analysis_markets = analysis.markets
        item.analysis_direction = analysis.direction
        item.analysis_reason = analysis.reason
        item.analysis_rule_hits = analysis.rule_hits

    apply_rules_to_item = apply_to_item

    @staticmethod
    def is_high_level(level: str, threshold: str = "A") -> bool:
        return LEVEL_SCORE.get(level.upper(), 1) >= LEVEL_SCORE.get(threshold.upper(), 3)

    def _analyze_rules(self, content: str) -> NewsAnalysis:
        lowered = content.casefold()
        matched_rules = [rule for rule in RULES if any(keyword.casefold() in lowered for keyword in rule.keywords)]
        if not matched_rules:
            return NewsAnalysis()

        best_level = max(matched_rules, key=lambda rule: LEVEL_SCORE.get(rule.level, 1)).level
        markets = self._unique(part for rule in matched_rules for part in rule.markets)
        rule_hits = [rule.name for rule in matched_rules]
        reason = matched_rules[0].reason
        if len(matched_rules) > 1:
            reason = f"{reason} 同时命中：{', '.join(rule_hits[:3])}。"

        return NewsAnalysis(
            level=best_level,
            markets=markets,
            direction=self._infer_direction(lowered),
            reason=reason,
            rule_hits=rule_hits,
        )

    @staticmethod
    def _infer_direction(lowered_content: str) -> str:
        positive = any(term.casefold() in lowered_content for term in POSITIVE_TERMS)
        negative = any(term.casefold() in lowered_content for term in NEGATIVE_TERMS)
        if positive and not negative:
            return "偏利多"
        if negative and not positive:
            return "偏利空"
        if positive and negative:
            return "中性"
        return "不确定"

    @staticmethod
    def _unique(values) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
