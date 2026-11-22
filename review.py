#!/usr/bin/env python3
"""Run an offline, evidence-linked review of locally supplied media."""
import argparse
import base64
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from report import render
from rules import detect

BASE = Path(__file__).resolve().parent
CATEGORIES = {"bot", "link", "payment", "approval"}
EXTENSIONS = {
    "image": {".png", ".jpg", ".jpeg"},
    "video": {".mp4", ".mov", ".m4v", ".webm", ".mkv"},
}
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_FRAMES = 600


def run_tool(command, *, data=None, timeout=120):
    try:
        result = subprocess.run(command, input=data, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ValueError(f"缺少工具 {Path(command[0]).name}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{Path(command[0]).name} 超时") from exc
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} 退出码 {result.returncode}")
    return result.stdout


def read_config(manifest):
    config = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("sources"), list):
        raise ValueError("清单必须是含 sources 数组的 JSON 对象")
    if not config["sources"]:
        raise ValueError("清单中没有证据文件")
    return config


def source_paths(config, parent):
    ids = set()
    for entry in config["sources"]:
        source_id = entry.get("id", "")
        kind = entry.get("kind")
        raw_path = entry.get("path")
        if not isinstance(source_id, str) or not IDENTIFIER.fullmatch(source_id) or source_id in ids:
            raise ValueError("来源 id 必须唯一，并只用 ASCII 字母、数字、连字符或下划线")
        if kind not in EXTENSIONS or not isinstance(raw_path, str):
            raise ValueError(f"{source_id} 缺少有效来源类型或本地路径")
        if "://" in raw_path:
            raise ValueError(f"{source_id} 仅接受本地文件路径")
        path = (parent / raw_path).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS[kind]:
            raise ValueError(f"{source_id} 格式不受支持")
        ids.add(source_id)
        yield entry, path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("时间码必须是非负秒数")
    if not math.isfinite(value) or value < 0:
        raise ValueError("时间码必须是非负秒数")
    return round(float(value), 3)


def video_duration(path):
    raw = run_tool([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-select_streams", "v:0", "-show_entries", "stream=duration:format=duration",
        "-of", "json", str(path),
    ])
    meta = json.loads(raw)
    if not meta.get("streams"):
        raise ValueError("没有视频轨道")
    value = meta["streams"][0].get("duration")
    if not value or value == "N/A":
        value = meta.get("format", {}).get("duration")
    if value is None or value == "N/A":
        raise ValueError("无法取得视频时长")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError("无法取得视频时长")
    return result


def video_points(entry, duration, step, review_times):
    points = {seconds(t) for t in entry.get("checkpoints", [])}
    points.update(review_times)
    uniform_count = math.ceil(duration / step)
    if uniform_count > MAX_VIDEO_FRAMES + 1:
        raise ValueError(f"视频采样超过 {MAX_VIDEO_FRAMES} 帧，请调整 --interval")
    points.update(round(i * step, 3) for i in range(uniform_count)
                  if i * step < duration - 0.05)
    if max(points, default=0) >= duration:
        raise ValueError("有时间码超出视频时长")
    if len(points) > MAX_VIDEO_FRAMES:
        raise ValueError(f"视频采样超过 {MAX_VIDEO_FRAMES} 帧，请调整 --interval")
    return sorted(points)


def video_frame(path, timestamp):
    return run_tool([
        "ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-ss", f"{max(0, timestamp - 0.00055):.6f}", "-i", str(path),
        "-map", "0:v:0", "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
        "-f", "image2pipe", "-c:v", "png", "pipe:1",
    ], timeout=25)


def helper_binary(explicit):
    if explicit:
        return explicit.resolve(strict=True)
    build = BASE / ".build"
    build.mkdir(exist_ok=True)
    helper = build / "vision-ocr"
    swift = BASE / "ocr.swift"
    if not helper.exists() or helper.stat().st_mtime_ns < swift.stat().st_mtime_ns:
        run_tool(["swiftc", "-O", str(swift), "-o", str(helper)], timeout=160)
    return helper


def collect_ocr(helper, shots):
    payload = []
    for shot_id, blob in shots:
        payload.append(json.dumps({
            "id": shot_id,
            "data": base64.b64encode(blob).decode("ascii"),
        }))
    # Raw text exists in this process only. Do not return it to the report.
    raw = run_tool([str(helper)], data=("\n".join(payload) + "\n").encode(), timeout=400)
    parsed = {}
    for row in raw.splitlines():
        item = json.loads(row)
        if item.get("id") in parsed:
            raise ValueError("OCR 返回了重复的图片标识")
        parsed[item["id"]] = item
    if set(parsed) != {shot_id for shot_id, _ in shots}:
        raise ValueError("OCR 未回传所有图片标识")
    return parsed


def verified_box(box):
    if box is None:
        return None
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("坐标必须是 [x,y,w,h] 或 null")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v < 0 or v > 1 for v in box):
        raise ValueError("坐标必须在 0 到 1 之间")
    if (box[2] <= 0 or box[3] <= 0 or box[0] + box[2] > 1.000001
            or box[1] + box[3] > 1.000001):
        raise ValueError("坐标框超出画面")
    return box


def review_items(config, sources):
    by_id = {source["id"]: source for source in sources}
    for item in config.get("reviewed", []):
        source = by_id.get(item.get("source_id"))
        if source is None:
            raise ValueError("人工条目引用了未知来源")
        category = item.get("category")
        status = item.get("status")
        grade = item.get("grade")
        if category not in CATEGORIES or (status, grade) not in {
            ("observed", "E2"), ("pending", "E0"), ("pending", "E1"),
        }:
            raise ValueError("人工条目的类别、状态或证据等级无效")
        timestamp = item.get("timestamp")
        if source["kind"] == "video":
            timestamp = seconds(timestamp)
            if timestamp >= source["duration"]:
                raise ValueError("人工条目时间码超出视频时长")
        elif timestamp is not None:
            raise ValueError("图片来源不设视频时间码")
        title = item.get("title")
        summary = item.get("summary")
        if not isinstance(title, str) or not title.strip() or not isinstance(summary, str):
            raise ValueError("人工条目需要标题和说明")
        yield {
            "source_id": source["id"], "category": category, "status": status,
            "grade": grade, "title": title, "summary": summary, "timestamp": timestamp,
            "box": verified_box(item.get("box")), "method": "review",
        }


def ocr_items(result, locations, step):
    last = {}
    for shot_id, source_id, timestamp in locations:
        packet = result[shot_id]
        if packet.get("error"):
            continue
        for clue in detect(packet.get("lines", [])):
            key = (source_id, clue["rule"])
            if timestamp is not None:
                prior = last.get(key)
                last[key] = timestamp
                if prior is not None and timestamp - prior <= max(step * 1.55, 1):
                    continue
            yield {**clue, "source_id": source_id, "timestamp": timestamp, "method": "ocr"}


def scan(manifest, helper, interval):
    config = read_config(manifest)
    files = list(source_paths(config, manifest.parent))
    sources = []
    for entry, path in files:
        source = {
            "id": entry["id"], "label": str(entry.get("label", entry["id"])),
            "kind": entry["kind"], "reference": str(entry.get("reference", "")),
            "file_url": path.as_uri(), "sha256": sha256(path),
        }
        if entry["kind"] == "video":
            source["duration"] = video_duration(path)
        sources.append(source)

    reviewed = list(review_items(config, sources))
    cue_times = {}
    for item in reviewed:
        if item["timestamp"] is not None:
            cue_times.setdefault(item["source_id"], set()).add(item["timestamp"])

    locations = []
    shots = []
    warnings = []
    for source, (entry, path) in zip(sources, files):
        if source["kind"] == "image":
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError(f"{source['id']} 超出图像大小限制")
            locations.append((source["id"], source["id"], None))
            shots.append((source["id"], path.read_bytes()))
            continue
        points = video_points(entry, source["duration"], interval, cue_times.get(source["id"], set()))
        for ix, timestamp in enumerate(points):
            shot_id = f"{source['id']}/{ix}"
            blob = video_frame(path, timestamp)
            if not blob:
                warnings.append(f"{source['id']} 在 {timestamp:.3f} 秒未取到帧")
                continue
            locations.append((shot_id, source["id"], timestamp))
            shots.append((shot_id, blob))

    if not shots:
        raise ValueError("没有可识别的画面")
    result = collect_ocr(helper, shots)
    errors = [shot_id for shot_id, packet in result.items() if packet.get("error")]
    for shot_id in errors:
        warnings.append(f"{shot_id} OCR 失败")
    for source, (_, path) in zip(sources, files):
        if sha256(path) != source["sha256"]:
            raise ValueError(f"{source['id']} 分析期间发生变化，请用稳定副本重试")

    findings = reviewed + list(ocr_items(result, locations, interval))
    finding_counts = Counter(item["category"] for item in findings)
    for number, item in enumerate(findings, 1):
        item["id"] = f"F{number:04d}"
    return {
        "title": str(config.get("title", "Telegram 防骗证据复核")),
        "mode": str(config.get("mode", "local")),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": sources,
        "findings": findings,
        "coverage": {
            "images": sum(source["kind"] == "image" for source in sources),
            "videos": sum(source["kind"] == "video" for source in sources),
            "frames": sum(timestamp is not None for _, _, timestamp in locations),
            "interval_seconds": interval,
            "reviewed": len(reviewed),
            "ocr_errors": len(errors),
            "warnings": warnings,
            "categories": dict(finding_counts),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="本地 JSON 清单")
    parser.add_argument("--output", required=True, type=Path, help="新建报告目录")
    parser.add_argument("--interval", type=float, default=3, help="视频取样步长（秒）")
    parser.add_argument("--ocr-bin", type=Path, help="已有的 JSONL OCR 助手")
    args = parser.parse_args()
    try:
        if not math.isfinite(args.interval) or args.interval < 0.25:
            raise ValueError("--interval 必须至少为 0.25 秒")
        output = args.output.resolve()
        if output.exists():
            raise ValueError("输出目录已存在，请为本次扫描指定新目录")
        report = scan(args.manifest.resolve(strict=True), helper_binary(args.ocr_bin), args.interval)
        html = render(report)
        output.mkdir(parents=True, exist_ok=False)
        (output / "findings.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        (output / "report.html").write_text(html, encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"扫描失败：{exc}", file=sys.stderr)
        return 1
    coverage = report["coverage"]
    print(f"完成：{coverage['images']} 图，{coverage['videos']} 视频，"
          f"{coverage['frames']} 视频采样帧，{len(report['findings'])} 条线索")
    print(f"报告：{output / 'report.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
