#!/usr/bin/env python3
"""Merge IR search results into result_002.json and result_003.json."""
import json
import sys

# Mapping: stock_code -> ir_url (or null)
# This will be populated from the sub-agent results
IR_RESULTS = {}

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved: {path}")

def merge_results(json_path, ir_map):
    data = load_json(json_path)
    updated = 0
    for entry in data:
        code = entry["code"]
        if code in ir_map:
            url = ir_map[code]
            if url:
                entry["ir_url"] = url
                entry["method"] = "agent_web_search"
                entry["notes"] = "agent WebSearch 发现 IR 页面"
            else:
                entry["ir_url"] = None
                entry["method"] = "agent_web_search"
                entry["notes"] = "agent WebSearch 未找到独立 IR 页面，默认仅交易所/巨潮披露"
            updated += 1
    save_json(json_path, data)
    return updated

def main():
    if len(sys.argv) < 2:
        print("Usage: python merge_ir_results.py '<json_mapping>'")
        print("Example: python merge_ir_results.py '{\"000858\":\"https://...\",\"000568\":null}'")
        sys.exit(1)

    ir_map = json.loads(sys.argv[1])
    print(f"Loaded {len(ir_map)} IR mappings")

    r2 = "/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/data/ir_batches/result_002.json"
    r3 = "/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/data/ir_batches/result_003.json"

    u2 = merge_results(r2, ir_map)
    u3 = merge_results(r3, ir_map)
    print(f"Updated: result_002={u2}, result_003={u3}, total={u2+u3}")

if __name__ == "__main__":
    main()
