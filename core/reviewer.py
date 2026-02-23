# core/reviewer.py — 复核决策：仅对被拦项 y/n/all/none，返回 to_produce 与 to_reject
import logging
from typing import List, Dict, Any, Tuple

from inputimeout import inputimeout, TimeoutOccurred

logger = logging.getLogger(__name__)

VALID_INPUTS = frozenset({"y", "n", "all", "none"})

RED = "\033[31m"
RESET = "\033[0m"


def ask_one(prompt: str, timeout: int = 600, valid: frozenset = VALID_INPUTS) -> str:
    """循环询问直到得到 valid 中之一或超时。超时返回 'none'。"""
    while True:
        try:
            user_input = inputimeout(prompt=prompt, timeout=timeout).strip().lower()
        except TimeoutOccurred:
            print("\n检测到响应超时，已自动执行 [none] 策略，物料已移至废片库。")
            logger.warning("Timeout Emergency Stop: 600s 无有效输入，已自动执行 [none] 策略")
            return "none"
        if user_input in valid:
            logger.info("厂长决策指令: %s", user_input)
            return user_input
        logger.warning("无效指令 [%s]，要求重新输入 (y/n/all/none)", user_input or "(空回车)")
        print(f"⚠️ 无效指令 [{user_input or '(空回车)'}]！请重新输入 (y/n/all/none): ")


def review_blocked(
    blocked: List[Dict[str, Any]],
    gate: float,
    timeout_seconds: int = 600,
) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
    """
    对被拦项逐项询问 y/n/all/none，返回 (to_produce, to_reject)。
    to_reject 每项为 (item, reason)，reason 为 'quality' 或 'duplicate'。
    """
    to_produce: List[Dict[str, Any]] = []
    to_reject: List[Tuple[Dict[str, Any], str]] = []
    if not blocked:
        return to_produce, to_reject
    print("\n⏳ [交互复核] 仅接受 y / n / all / none；600 秒无响应将自动执行 [none]。")
    remaining = list(blocked)
    while remaining:
        item = remaining[0]
        name = item["filename"]
        if item.get("is_duplicate"):
            reason = f"重复 曾于批次 {item.get('duplicate_batch_id', '')} ({item.get('duplicate_created_at', '')})"
        else:
            reason = f"不合格 得分: {item['score']:.1f}% / 准入: {gate}%"
        prompt = f"\n当前: {name} - {reason}\n"
        # 规则分项：未达标项标红
        rule_stats = item.get("rule_stats") or {}
        if rule_stats:
            for rule_name, info in [
                ("brightness", "亮度"),
                ("blur", "模糊"),
                ("jitter", "抖动"),
                ("contrast", "对比度"),
            ]:
                r = rule_stats.get(rule_name)
                if not r:
                    continue
                if r.get("pass"):
                    if rule_name == "brightness":
                        prompt += f"  {info}: 正常 ({r.get('min', 0):.1f}~{r.get('max', 0):.1f})\n"
                    elif rule_name == "blur":
                        prompt += f"  {info}: 正常 (最低 {r.get('min', 0):.1f}≥{r.get('threshold', 0)})\n"
                    elif rule_name == "jitter":
                        prompt += f"  {info}: 正常 (最高 {r.get('max', 0):.1f}≤{r.get('threshold', 0)})\n"
                    else:
                        prompt += f"  {info}: 正常\n"
                else:
                    fail = r.get("fail_reason") or "未达标"
                    prompt += f"  {RED}{info}: {fail}{RESET}\n"
        prompt += "  [y]放行 [n]丢弃 (y/n/all/none) [600s后默认none]: "
        cmd = ask_one(prompt, timeout=timeout_seconds)
        if cmd == "y":
            to_produce.append(item)
            remaining.pop(0)
        elif cmd == "n":
            to_reject.append((item, "duplicate" if item.get("is_duplicate") else "quality"))
            remaining.pop(0)
        elif cmd == "all":
            to_produce.extend(remaining)
            remaining.clear()
            print("已选择 [all]，剩余被拦项全部放行。")
        else:
            for x in remaining:
                to_reject.append((x, "duplicate" if x.get("is_duplicate") else "quality"))
            remaining.clear()
            print("已选择 [none]，剩余被拦项全部丢弃（不合格→废片库，重复→冗余库）。")
    return to_produce, to_reject
