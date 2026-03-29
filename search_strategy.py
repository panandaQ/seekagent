from __future__ import annotations


def generate_queries(name: str, affiliation: str = "") -> list[str]:
    cleaned_name = name.strip()
    cleaned_aff = affiliation.strip()

    if not cleaned_name:
        return []

    queries: list[str] = []
    if cleaned_aff:
        queries.append(f'"{cleaned_name}" "{cleaned_aff}" 计算机')
        queries.append(f"{cleaned_name} {cleaned_aff} 个人主页")
    else:
        queries.append(f'"{cleaned_name}" 计算机')
        queries.append(f"site:.cn {cleaned_name}")

    queries.append(f"{cleaned_name} 百度百科 计算机")
    queries.append(f"{cleaned_name} 邮箱 联系方式")
    queries.append(f"{cleaned_name} 信息科学 学者")

    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    return deduped[:6]
