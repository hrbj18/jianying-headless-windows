"""歌词对齐与切分的单元测试。

用例数据取自真实工程：12 句本地识别歌词 + 6 张官方歌词模板卡，
期望结果与人工核对过的映射一致（t6←1、t7←2、t8←3,4、t9←5,6、t10←7,8、t11←9,10,11）。
"""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("lyrics_align", ROOT / "engine/lyrics_align.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# (start_ms, end_ms, text)，来自 work/测试-auto-lyrics-large-v3/lyrics.json
CUE_SPANS = [
    (0, 2820, "有些旧约不必再封"),
    (6080, 8300, "于是不觉可问春风"),
    (8300, 10460, "它掠过我空袖口春风"),
    (10460, 12760, "添我十万八千梦"),
    (13130, 15100, "走向没有你的岸"),
    (15100, 16940, "各起重山各起重梦"),
    (16940, 19480, "终于不问归程"),
    (20010, 21860, "还会等到有理想"),
    (21860, 23920, "缺陷天边一番红人"),
    (23920, 26140, "长大后才知晓"),
    (26800, 28900, "这一程虚有我"),
    (28900, 31200, "自封"),
]

# (id, start_ms, end_ms, 原槽位文本)，来自 canonical XML
CARD_SPANS = [
    ("t6", 6466, 7899, ["遇事", "不决 ", "可问春风"]),
    ("t7", 7900, 10100, ["它掠过", "我空", "袖口"]),
    ("t8", 10100, 15233, ["春风填我 十", "万八", "千梦", "\n走向没", "有你", "的岸"]),
    ("t9", 15233, 20099, ["隔几", "隔几", "重山隔", "重山隔", "几重梦", "几重梦", "几重梦",
                          "\n终于", "不问", "归程"]),
    ("t10", 20500, 23766, ["还未等", "到檐铃响\n", "却见天边", "已放红"]),
    ("t11", 23766, 31566, [" 人长大", "后才", "知晓", "\n这一程须", "由我自封"]),
]


def make_cues():
    cues = []
    for index, (start, end, text) in enumerate(CUE_SPANS):
        words = [{"text": char, "start_ms": start, "end_ms": end} for char in text]
        cues.append({"id": f"lyric_{index:04d}", "text": text, "start_ms": start,
                     "end_ms": end, "words": words})
    return cues


def make_cards():
    return [{"id": card_id, "start_ms": start, "end_ms": end, "slots": len(slots),
             "weights": [len(text) for text in slots]}
            for card_id, start, end, slots in CARD_SPANS]


class AlignmentTests(unittest.TestCase):
    def test_matches_reviewed_mapping(self):
        mapping, report = MODULE.align_cards(make_cards(), make_cues())
        self.assertEqual(mapping, {"t6": [1], "t7": [2], "t8": [3, 4],
                                   "t9": [5, 6], "t10": [7, 8], "t11": [9, 10, 11]})
        self.assertEqual(report["outside_cue_indices"], [0])
        self.assertEqual(report["aligned_cards"], 6)
        self.assertEqual(report["skipped_cards"], 0)
        self.assertTrue(all(row["status"] == "aligned" for row in report["cards"]))

    def test_segments_rebuild_source_text(self):
        mapping, report = MODULE.align_cards(make_cards(), make_cues())
        cues = make_cues()
        rows = {row["id"]: row for row in report["cards"]}
        for card_id, indices in mapping.items():
            text = "".join(cue["text"] for cue in (cues[i] for i in indices))
            self.assertEqual("".join(rows[card_id]["segments"]), text)

    def test_skips_card_without_lyrics(self):
        cards = [{"id": "t1", "start_ms": 0, "end_ms": 500, "slots": 1, "weights": [1]},
                 {"id": "t2", "start_ms": 6000, "end_ms": 8000, "slots": 2, "weights": [1, 1]}]
        mapping, report = MODULE.align_cards(cards, make_cues())
        self.assertEqual(mapping, {"t2": [1]})
        rows = {row["id"]: row for row in report["cards"]}
        self.assertEqual(rows["t1"]["status"], "skipped")
        self.assertIn("没有歌词句", rows["t1"]["reason"])

    def test_skips_card_when_words_below_slots(self):
        cards = [{"id": "t6", "start_ms": 6466, "end_ms": 7899, "slots": 12,
                  "weights": [1] * 12}]
        mapping, report = MODULE.align_cards(cards, make_cues())
        self.assertEqual(mapping, {})
        self.assertIn("少于槽位", report["cards"][0]["reason"])

    def test_rejects_card_far_from_its_cues(self):
        # 5000..5500ms 之间没有任何歌词句的时间中心（上一句中心 1410，下一句 7190）。
        cards = [{"id": "t6", "start_ms": 5000, "end_ms": 5500, "slots": 2, "weights": [1, 1]}]
        mapping, report = MODULE.align_cards(cards, make_cues())
        self.assertEqual(mapping, {})
        self.assertEqual(report["cards"][0]["status"], "skipped")
        self.assertIn("没有歌词句", report["cards"][0]["reason"])


class SplitTests(unittest.TestCase):
    def test_split_keeps_slot_count_and_text(self):
        words = [{"text": char} for char in "于是不觉可问春风"]
        segments = MODULE.split_by_weights(words, [2, 3, 4])
        self.assertEqual(len(segments), 3)
        self.assertEqual("".join(segments), "于是不觉可问春风")
        self.assertTrue(all(segment for segment in segments))

    def test_split_returns_none_when_too_few_words(self):
        words = [{"text": char} for char in "一二"]
        self.assertIsNone(MODULE.split_by_weights(words, [1, 1, 1]))

    def test_split_never_returns_empty_slot(self):
        words = [{"text": char} for char in "甲" * 5]
        segments = MODULE.split_by_weights(words, [9, 1])
        self.assertEqual(len(segments), 2)
        self.assertTrue(all(segment for segment in segments))


class OverlapTests(unittest.TestCase):
    def test_ratio_bounds(self):
        self.assertEqual(MODULE.overlap_ratio(0, 100, 0, 100), 1.0)
        self.assertEqual(MODULE.overlap_ratio(0, 100, 200, 300), 0.0)
        self.assertAlmostEqual(MODULE.overlap_ratio(0, 100, 50, 150), 0.5)
        self.assertEqual(MODULE.overlap_ratio(0, 0, 0, 100), 0.0)


if __name__ == "__main__":
    unittest.main()
