from collections import Counter

CATEGORY_KEYWORDS = {
    "教务": {
        "学籍", "考试", "成绩", "课程", "选课", "退课", "学分", "注册",
        "缓考", "重修", "补考", "教学", "培养方案", "毕业", "学位", "课表",
    },
    "学工": {
        "奖助", "奖学金", "助学金", "助学贷款", "勤工", "请假", "纪律",
        "评优", "学生事务", "辅导员", "处分", "综合素质", "困难认定",
    },
    "后勤": {
        "宿舍", "维修", "校园卡", "图书馆", "网络", "医疗", "校医院",
        "食堂", "后勤", "报修", "门禁", "停车", "打印", "饮水",
    },
    "跨部门": {
        "跨部门", "新生", "入学", "报到", "衔接", "综合服务", "一站式",
        "多个系统", "FAQ", "问答", "校园服务",
    },
}


def classify_document(title: str, filename: str) -> str:
    text = f"{title} {filename}".lower()
    scores: Counter[str] = Counter()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                scores[category] += 3 if keyword in title else 1
    if not scores:
        return "跨部门"
    maximum = max(scores.values())
    winners = [category for category, score in scores.items() if score == maximum]
    return winners[0] if len(winners) == 1 else "跨部门"
