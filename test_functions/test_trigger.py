import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Time utils
# -----------------------------

def parse_hhmm(s: str) -> int:
    """'08:33' -> minutes since day start"""
    h, m = s.split(":")
    return int(h) * 60 + int(m)

def fmt_hhmm(mins: int) -> str:
    h = mins // 60
    m = mins % 60
    return f"{h:02d}:{m:02d}"

def safe_get(d: Dict[str, Any], key: str, default=None):
    return d.get(key, default)


# -----------------------------
# Output schema
# -----------------------------

@dataclass
class FeedbackUI:
    type: str                # "corner_bubble" | "toast" | "popup" | "daily_card"
    ttl_sec: int = 6
    can_close: bool = True
    intensity: str = "light" # "light" | "medium" | "strong"

@dataclass
class FeedbackEvent:
    event_id: str
    time_local: str
    time_minute_of_day: int
    trigger_type: str        # focus | return_to_work | first_work | anomaly
    level: str               # L1 | L2 | L3
    ui: FeedbackUI
    message: str
    evidence_segment_ids: List[str]
    project_id: Optional[str] = None
    confidence: float = 0.8
    cooldown_minutes: int = 30


# -----------------------------
# Gemini gate (placeholder)
# -----------------------------

def gemini_gate(
    trigger_type: str,
    candidate: FeedbackEvent,
    day_timeline: Dict[str, Any],
) -> Tuple[bool, FeedbackEvent]:
    """
    Hackathon MVP: always approve.
    Later: call Gemini to decide should_send + rewrite message/ui.
    """
    return True, candidate


# -----------------------------
# Work inference (compat with your schema)
# -----------------------------

DEFAULT_WORK_ACTIVITIES = {"Coding", "Writing/Reading"}

def infer_is_work(seg: Dict[str, Any]) -> bool:
    # If you later add seg["is_work"], this will automatically use it.
    if "is_work" in seg:
        return bool(seg["is_work"])
    act = safe_get(seg, "activity", "")
    return act in DEFAULT_WORK_ACTIVITIES

def infer_project_id(seg: Dict[str, Any]) -> Optional[str]:
    # If you later add seg["project_id"], it will be used.
    return seg.get("project_id")


# -----------------------------
# Cooldown manager
# -----------------------------

class CooldownTracker:
    def __init__(self):
        self.last_sent_at: Dict[str, int] = {}  # key -> minute_of_day

    def can_send(self, key: str, now_min: int, cooldown_min: int) -> bool:
        last = self.last_sent_at.get(key)
        if last is None:
            return True
        return (now_min - last) >= cooldown_min

    def mark_sent(self, key: str, now_min: int):
        self.last_sent_at[key] = now_min


# -----------------------------
# Trigger detectors
# -----------------------------

def detect_first_work(segments: List[Dict[str, Any]], cd: CooldownTracker) -> List[FeedbackEvent]:
    for seg in segments:
        if infer_is_work(seg):
            start_min = parse_hhmm(seg["start_time_local"])
            if cd.can_send("first_work", start_min, 24 * 60):
                ui = FeedbackUI(type="corner_bubble", ttl_sec=6, can_close=True, intensity="light")
                ev = FeedbackEvent(
                    event_id=f"firstwork_{seg.get('segment_id','')}",
                    time_local=seg["start_time_local"],
                    time_minute_of_day=start_min,
                    trigger_type="first_work",
                    level="L1",
                    ui=ui,
                    message="开始干活啦～今天也一起把重要的事推进一点点。",
                    evidence_segment_ids=[seg.get("segment_id","")],
                    project_id=infer_project_id(seg),
                    confidence=0.75,
                    cooldown_minutes=24 * 60
                )
                cd.mark_sent("first_work", start_min)
                return [ev]
            break
    return []

def detect_focus_levels(
    segments: List[Dict[str, Any]],
    cd: CooldownTracker,
    thresholds: List[int] = [15, 25, 40]
) -> List[FeedbackEvent]:
    """
    Continuous focus encouragement:
      - When consecutive work minutes crosses 15/25/40 -> L1/L2/L3
    """
    events: List[FeedbackEvent] = []
    consecutive = 0
    emitted = set()
    chain_ids: List[str] = []
    cur_project: Optional[str] = None

    for seg in segments:
        s_id = seg.get("segment_id","")
        start_min = parse_hhmm(seg["start_time_local"])
        end_min = parse_hhmm(seg["end_time_local"])
        dur = int(seg.get("duration_minutes", max(0, end_min - start_min)))

        if infer_is_work(seg):
            consecutive += dur
            chain_ids.append(s_id)
            cur_project = infer_project_id(seg) or cur_project

            for i, th in enumerate(thresholds):
                level = f"L{i+1}"
                key = f"focus_{level}"
                if consecutive >= th and level not in emitted and cd.can_send(key, end_min, 30):
                    ui = FeedbackUI(
                        type="corner_bubble",
                        ttl_sec=6,
                        can_close=True,
                        intensity="light" if level == "L1" else "medium"
                    )
                    msg = {
                        "L1": f"你已经连续专注了 {th} 分钟，节奏很稳。",
                        "L2": f"专注到 {th} 分钟了！继续保持这个状态。",
                        "L3": f"你已经专注了 {th} 分钟，今天的推进很扎实。",
                    }[level]

                    ev = FeedbackEvent(
                        event_id=f"focus_{s_id}_{level}",
                        time_local=seg["end_time_local"],
                        time_minute_of_day=end_min,
                        trigger_type="focus",
                        level=level,
                        ui=ui,
                        message=msg,
                        evidence_segment_ids=chain_ids[-6:],
                        project_id=cur_project,
                        confidence=0.85,
                        cooldown_minutes=30
                    )
                    events.append(ev)
                    cd.mark_sent(key, end_min)
                    emitted.add(level)
        else:
            # Break focus chain
            consecutive = 0
            emitted.clear()
            chain_ids = []
            cur_project = None

    return events

def detect_return_to_work(
    segments: List[Dict[str, Any]],
    cd: CooldownTracker,
    min_offwork_minutes: int = 5
) -> List[FeedbackEvent]:
    """
    Off-work >= 5 minutes then return to work -> L2 toast
    """
    events: List[FeedbackEvent] = []
    off_min = 0
    off_ids: List[str] = []
    was_off = False

    for seg in segments:
        s_id = seg.get("segment_id","")
        start_min = parse_hhmm(seg["start_time_local"])
        end_min = parse_hhmm(seg["end_time_local"])
        dur = int(seg.get("duration_minutes", max(0, end_min - start_min)))

        if not infer_is_work(seg):
            was_off = True
            off_min += dur
            off_ids.append(s_id)
        else:
            if was_off and off_min >= min_offwork_minutes and cd.can_send("return_to_work", start_min, 30):
                ui = FeedbackUI(type="toast", ttl_sec=6, can_close=True, intensity="medium")
                msg = f"欢迎回来～你刚刚离开工作页面 {off_min} 分钟，继续把这一段收尾就很棒。"
                ev = FeedbackEvent(
                    event_id=f"return_{s_id}",
                    time_local=seg["start_time_local"],
                    time_minute_of_day=start_min,
                    trigger_type="return_to_work",
                    level="L2",
                    ui=ui,
                    message=msg,
                    evidence_segment_ids=off_ids[-6:] + [s_id],
                    project_id=infer_project_id(seg),
                    confidence=0.8,
                    cooldown_minutes=30
                )
                events.append(ev)
                cd.mark_sent("return_to_work", start_min)

            # reset
            was_off = False
            off_min = 0
            off_ids = []

    return events

def detect_anomaly_switching(
    segments: List[Dict[str, Any]],
    cd: CooldownTracker,
    window_minutes: int = 60,
    switch_threshold: int = 6
) -> List[FeedbackEvent]:
    """
    1 hour window: work/non-work switches >= threshold -> candidate anomaly trigger
    """
    events: List[FeedbackEvent] = []

    switches = 0
    prev: Optional[bool] = None
    window_start: Optional[int] = None
    window_ids: List[str] = []

    for seg in segments:
        s_id = seg.get("segment_id","")
        start_min = parse_hhmm(seg["start_time_local"])
        end_min = parse_hhmm(seg["end_time_local"])
        cur = infer_is_work(seg)

        if window_start is None:
            window_start = start_min

        window_ids.append(s_id)
        if prev is not None and cur != prev:
            switches += 1
        prev = cur

        if end_min - window_start >= window_minutes:
            if switches >= switch_threshold and cd.can_send("anomaly_switching", end_min, 60):
                ui = FeedbackUI(type="toast", ttl_sec=6, can_close=True, intensity="medium")
                msg = "你这一小时切换有点频繁，先选一个最小任务推进 10 分钟，会更轻松。"
                ev = FeedbackEvent(
                    event_id=f"anomaly_{s_id}",
                    time_local=seg["end_time_local"],
                    time_minute_of_day=end_min,
                    trigger_type="anomaly",
                    level="L2",
                    ui=ui,
                    message=msg,
                    evidence_segment_ids=window_ids[-12:],
                    project_id=None,
                    confidence=0.7,
                    cooldown_minutes=60
                )
                events.append(ev)
                cd.mark_sent("anomaly_switching", end_min)

            # reset window
            switches = 0
            prev = None
            window_start = None
            window_ids = []

    return events


# -----------------------------
# Main generator
# -----------------------------

def generate_feedback_events(day_timeline: Dict[str, Any]) -> Dict[str, Any]:
    segments = day_timeline.get("timeline_segments", [])
    segments = sorted(segments, key=lambda s: parse_hhmm(s["start_time_local"]))

    cd = CooldownTracker()

    candidates: List[FeedbackEvent] = []
    candidates += detect_first_work(segments, cd)
    candidates += detect_focus_levels(segments, cd, thresholds=[15, 25, 40])
    candidates += detect_return_to_work(segments, cd, min_offwork_minutes=5)
    candidates += detect_anomaly_switching(segments, cd)

    final_events: List[FeedbackEvent] = []
    for ev in candidates:
        ok, ev2 = gemini_gate(ev.trigger_type, ev, day_timeline)
        if ok:
            final_events.append(ev2)

    final_events.sort(key=lambda e: e.time_minute_of_day)

    return {
        "schema_version": "1.0",
        "artifact_type": "feedback_events",
        "date_local": day_timeline.get("date_local"),
        "timezone": day_timeline.get("timezone"),
        "capture_interval_minutes": day_timeline.get("capture_interval_minutes"),
        "feedback_events": [asdict(e) for e in final_events],
    }


# -----------------------------
# CLI
# -----------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeline", required=True, help="Path to your DayTimeline JSON (schema v2.0)")
    parser.add_argument("--out", default="feedback_events.json", help="Output JSON path")
    args = parser.parse_args()

    with open(args.timeline, "r", encoding="utf-8") as f:
        day_timeline = json.load(f)

    out = generate_feedback_events(day_timeline)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote {args.out} with {len(out['feedback_events'])} events")

if __name__ == "__main__":
    main()
