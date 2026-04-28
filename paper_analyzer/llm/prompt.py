from paper_analyzer.utils.config import load_research_topic


def build_prompt(text: str, research_topic: str | None = None) -> str:
    topic = research_topic or load_research_topic()
    return f"""请分析下面这篇论文内容，并且只输出合法 JSON，不要输出 Markdown，不要添加解释。

如果原文中没有明确出现某个字段，请填入"未识别"，不要编造。

JSON 必须包含这些字段：
- first_author：第一作者姓名
- first_author_affiliation：第一作者院校/研究所
- second_author：第二作者姓名
- second_author_affiliation：第二作者院校/研究所
- corresponding_author：通讯作者姓名
- corresponding_author_affiliation：通讯作者院校/研究所
- publication_year：发表年份
- paper_title：论文标题
- venue：期刊/会议名称
- doi：DOI
- core_problem：本研究要解决的关键科学/技术问题
- core_hypotheses：作者提出的核心研究假设或理论构想，使用字符串数组
- research_approach：整体研究设计，包括理论、仿真、实验、案例等
- key_methods：关键方法/模型
- data_source_and_scale：数据来源与规模
- core_findings：最重要、最创新的科学发现
- main_conclusions：作者基于证据得出的最终结论
- field_contribution：对本领域的理论、方法或应用贡献
- relevance_to_my_research：和用户研究主题/综述方向的核心交集
- highlights：亮点/启发，使用字符串，不要使用数组
- limitations：局限/疑问，使用字符串，不要使用数组

用户研究主题：{topic}

论文内容：
{text}
"""
