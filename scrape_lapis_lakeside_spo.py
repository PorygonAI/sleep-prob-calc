"""抓取宝蓝湖畔一般出现睡姿及其普通地图 SPO。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAP_URL = "https://pks.raenonx.cc/zh/map/5"
SLEEPDEX_URL = "https://pks.raenonx.cc/en/sleepdex/lookup"
MAP_ID = 5
RANK_TITLES = {1: "普通", 2: "超級", 3: "高級", 4: "大師"}
LEVEL_ORDER = {
    **{f"普通{i}": i - 1 for i in range(1, 6)},
    **{f"超級{i}": i + 4 for i in range(1, 6)},
    **{f"高級{i}": i + 9 for i in range(1, 6)},
    **{f"大師{i}": i + 14 for i in range(1, 21)},
}
CSV_FIELDS = [
    "internalId",
    "pokemon_id",
    "pokemon_name",
    "rarity",
    "sleep_style_name",
    "snorlax_level",
    "level_order",
    "is_on_snorlax",
    "is_leader_exclusion",
    "spo_id",
    "spo",
]


class ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.in_script = False
        self.parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() == "script":
            self.in_script = True
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_script:
            self.scripts.append("".join(self.parts))
            self.in_script = False
            self.parts = []


def fetch_html(url: str, timeout: float = 30.0, attempts: int = 3) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/136.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt)
    raise RuntimeError(f"下载失败：{url}（{last_error}）")


def extract_flight_text(html: str) -> str:
    """解码 Next.js 写入 script 标签的 React Flight 字符串分片。"""
    parser = ScriptParser()
    parser.feed(html)
    decoder = json.JSONDecoder()
    marker = "self.__next_f.push("
    chunks: list[str] = []

    for script in parser.scripts:
        position = 0
        while True:
            marker_position = script.find(marker, position)
            if marker_position < 0:
                break
            value_position = marker_position + len(marker)
            try:
                value, value_end = decoder.raw_decode(script, value_position)
            except json.JSONDecodeError:
                position = value_position
                continue
            if (
                isinstance(value, list)
                and len(value) >= 2
                and isinstance(value[1], str)
            ):
                chunks.append(value[1])
            position = value_end

    if not chunks:
        raise ValueError("页面中没有找到 Next.js Flight 数据。")
    return "".join(chunks)


def extract_server_data(
    flight_text: str, required_keys: set[str]
) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    marker = '"serverData":'
    position = 0

    while True:
        marker_position = flight_text.find(marker, position)
        if marker_position < 0:
            break
        value_position = marker_position + len(marker)
        try:
            value, value_end = decoder.raw_decode(flight_text, value_position)
        except json.JSONDecodeError:
            position = value_position
            continue
        if isinstance(value, dict) and required_keys <= value.keys():
            return value
        position = value_end

    raise ValueError(
        "页面中没有找到包含以下字段的 serverData："
        + ", ".join(sorted(required_keys))
    )


def extract_named_object(flight_text: str, name: str) -> dict[str, Any]:
    marker = f'"{name}":'
    position = flight_text.find(marker)
    if position < 0:
        raise ValueError(f"页面中没有找到 {name} 翻译资料。")
    value, _ = json.JSONDecoder().raw_decode(
        flight_text, position + len(marker)
    )
    if not isinstance(value, dict):
        raise ValueError(f"{name} 翻译资料格式错误。")
    return value


def find_translation(flight_text: str, key: str) -> str:
    pattern = re.compile(r'"' + re.escape(key) + r'":("(?:\\.|[^"\\])*")')
    match = pattern.search(flight_text)
    return json.loads(match.group(1)) if match else key


def valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def estimate_legacy_spo(
    base: dict[str, Any], function_map: dict[str, Any]
) -> int:
    rewards = base["rewards"]
    definition = function_map["regular"][str(base["rarity"])]
    unrounded = definition["slope"] * (
        2 * rewards["researchExp"] + 10 / 9 * rewards["shards"]
    ) + definition["intercept"]
    # 前端 Math.round 对非负数等价于 floor(x + 0.5)。
    return math.floor(unrounded + 0.5)


def regular_spo(
    base: dict[str, Any],
    spo_remap: dict[str, Any],
    function_map: dict[str, Any],
) -> int:
    base_spo = base.get("spo", {}).get("regular")
    if valid_number(base_spo):
        return int(base_spo)

    spo_id = str(base["spoId"])
    remapped = (
        spo_remap.get(spo_id, {})
        .get("computed", {})
        .get("regular", {})
        .get("reference")
    )
    if valid_number(remapped):
        return int(remapped)

    estimated_legacy_spo = estimate_legacy_spo(base, function_map)
    if not valid_number(estimated_legacy_spo):
        raise ValueError(f"internalId={base['internalId']} 无法取得有效 SPO。")
    return estimated_legacy_spo


def build_rows(
    map_data: dict[str, Any],
    sleepdex_data: dict[str, Any],
    map_flight_text: str,
) -> list[dict[str, Any]]:
    flagged_map = sleepdex_data["sleepStyleFlaggedBaseDataMap"]
    spo_remap = sleepdex_data["spoRemapDataMap"]
    function_map = sleepdex_data["spoRemapFuncDefMap"]
    pokemon_names = extract_named_object(map_flight_text, "PokemonName")
    rows: list[dict[str, Any]] = []

    for linkage in map_data["sleepStyleLinkages"]:
        if linkage.get("mapId") != MAP_ID or linkage.get("type") != "regular":
            continue

        internal_id = str(linkage["sleepStyleInternalId"])
        flagged = flagged_map[internal_id]
        base = flagged["base"]
        flags = flagged["flags"]
        rank = linkage["minSnorlaxRank"]
        snorlax_level = f"{RANK_TITLES[rank['title']]}{rank['number']}"
        pokemon_id = int(base["pokedexId"])

        rows.append(
            {
                "internalId": int(base["internalId"]),
                "pokemon_id": pokemon_id,
                "pokemon_name": pokemon_names.get(str(pokemon_id), str(pokemon_id)),
                "rarity": int(base["rarity"]),
                "sleep_style_name": find_translation(
                    map_flight_text, str(base["i18nKey"])
                ),
                "snorlax_level": snorlax_level,
                "level_order": LEVEL_ORDER[snorlax_level],
                "is_on_snorlax": str(bool(base["isOnSnorlax"])).lower(),
                "is_leader_exclusion": str(
                    bool(flags.get("isLeaderExclusion", False))
                ).lower(),
                "spo_id": int(base["spoId"]),
                "spo": regular_spo(base, spo_remap, function_map),
            }
        )

    rows.sort(key=lambda row: int(row["internalId"]))
    return rows


def write_csv(rows: Iterable[dict[str, Any]], output: Path) -> int:
    materialized = list(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-url", default=MAP_URL)
    parser.add_argument("--sleepdex-url", default=SLEEPDEX_URL)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=script_dir / "lapis_lakeside_sleep_styles.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        map_flight = extract_flight_text(fetch_html(args.map_url))
        sleepdex_flight = extract_flight_text(fetch_html(args.sleepdex_url))
        map_data = extract_server_data(map_flight, {"sleepStyleLinkages"})
        sleepdex_data = extract_server_data(
            sleepdex_flight,
            {
                "sleepStyleFlaggedBaseDataMap",
                "spoRemapDataMap",
                "spoRemapFuncDefMap",
            },
        )
        rows = build_rows(map_data, sleepdex_data, map_flight)
        count = write_csv(rows, args.output)
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"已写入 {count} 条宝蓝湖畔一般出现睡姿：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
