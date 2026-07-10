"""批量 IR 页面发现脚本。

策略：
1. 市值前 500 家用 WebSearch 逐一发现
2. 其余 5000+ 家用默认规则（交易所+巨潮 URL），抽样验证
3. 结果写入 result_{batch}.json
"""

import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BATCH_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data/ir_batches"
)


def load_batch(idx: int) -> list[dict]:
    path = os.path.join(BATCH_DIR, f"batch_{idx:03d}.json")
    with open(path) as f:
        return json.load(f)


def save_result(idx: int, results: list[dict]):
    path = os.path.join(BATCH_DIR, f"result_{idx:03d}.json")
    with open(path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def default_result(companies: list[dict]) -> list[dict]:
    """对所有公司使用默认规则（交易所+巨潮）。"""
    return [
        {
            "code": c["code"],
            "name": c["name"],
            "ir_url": None,
            "method": "exchange_only",
            "notes": "默认：仅交易所/巨潮披露（待 agent 验证）",
        }
        for c in companies
    ]


def print_batch_for_agent(idx: int):
    """打印 batch 内容，供 agent 使用。"""
    companies = load_batch(idx)
    for c in companies:
        print(f"{c['code']}|{c['name']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "list":
        # 列出所有 batch 的统计
        for i in range(28):
            companies = load_batch(i)
            print(f"batch_{i:03d}: {len(companies)} companies")
    elif cmd == "dump":
        idx = int(sys.argv[2])
        print_batch_for_agent(idx)
    elif cmd == "init_results":
        # 为所有 batch 初始化默认结果（exchange_only）
        for i in range(28):
            companies = load_batch(i)
            results = default_result(companies)
            save_result(i, results)
            print(f"result_{i:03d}.json: {len(results)} records (default)")
    elif cmd == "help":
        print("Usage: python ir_batch_discovery.py <list|dump N|init_results>")
