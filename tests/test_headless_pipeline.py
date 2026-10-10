"""端到端流水线的离线单元测试（不调用剪映、不做 ASR）。"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
SPEC = importlib.util.spec_from_file_location("headless_pipeline", ROOT / "engine/headless_pipeline.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def scratch(prefix):
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" / "pipeline-tests"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))


XML = """<draft width="2276" height="1280">
  <main>
    <video id="v2" ref="video1" volume="0">
      <time material_start="0" duration="25133" speed="1" />
    </video>
  </main>
  <multi>
    <text id="t6">
      <time material_start="0" start="6466" duration="1433" />
      <template ref="text_template_lyrics1" />
      <content>
        <sub text="遇事" />
        <sub text="不决 " />
        <sub text="可问春风" />
      </content>
      <animation ref="anim_text1" animation_type="out" duration="150" />
    </text>
    <text id="t7">
      <time material_start="0" start="7900" duration="2200" />
      <template ref="text_template_lyrics1" />
      <content>
        <sub text="它掠过" />
        <sub text="我空" />
        <sub text="袖口" />
      </content>
    </text>
    <subtitle id="t1" font_ref="C:/fonts/a.ttf">
      <time material_start="0" start="0" duration="866" />
      <content><sub text="口播" /></content>
    </subtitle>
  </multi>
</draft>
"""

ALIGNMENT = {
    "cards": [
        {"id": "t6", "cues": [1], "slots": 3, "words": 8, "status": "aligned",
         "segments": ["于是", "不觉可", "问春风"]},
        {"id": "t7", "cues": [], "slots": 3, "words": 0, "status": "skipped",
         "reason": "卡时间窗内没有歌词句"},
    ],
    "outside_cue_indices": [0], "aligned_cards": 1, "skipped_cards": 1,
}


class CardSpecTests(unittest.TestCase):
    def test_reads_only_template_cards(self):
        cards = MODULE.card_specs(XML)
        self.assertEqual([card["id"] for card in cards], ["t6", "t7"])
        self.assertEqual(cards[0]["slots"], 3)
        self.assertEqual(cards[0]["weights"], [2, 3, 4])
        self.assertEqual((cards[0]["start_ms"], cards[0]["end_ms"]), (6466, 7899))
        self.assertEqual(cards[0]["template_ref"], "text_template_lyrics1")

    def test_rejects_timeline_without_template_cards(self):
        with self.assertRaises(ValueError):
            MODULE.card_specs("<draft><main></main><multi></multi></draft>")


class SelectionTests(unittest.TestCase):
    def test_selection_targets_aligned_cards_only(self):
        text, applied = MODULE.build_selection(MODULE.card_specs(XML), {"t6": [1], "t7": [2]},
                                               ALIGNMENT)
        self.assertEqual(applied, ["t6"])
        self.assertIn('draft.select("#t6 content").replaceChildrenXml(', text)
        self.assertIn("于是", text)
        self.assertTrue(text.rstrip().endswith("draft.apply();"))

    def test_selection_rewrites_original_time_window(self):
        # 整段替换 content 会让 apply 重算时长，因此必须显式写回 start/duration。
        text, _ = MODULE.build_selection(MODULE.card_specs(XML), {"t6": [1]}, ALIGNMENT)
        self.assertIn('draft.select("#t6 time").attr("start", "6466").attr("duration", "1433");',
                      text)

    def test_selection_escapes_xml_text(self):
        alignment = json.loads(json.dumps(ALIGNMENT))
        alignment["cards"][0]["segments"] = ["甲<&", "乙", "丙"]
        text, _ = MODULE.build_selection(MODULE.card_specs(XML), {"t6": [1]}, alignment)
        self.assertIn("甲&lt;&amp;", text)
        self.assertNotIn("甲<&", text)

    def test_tts_appends_speech_to_host(self):
        text, _ = MODULE.build_selection(MODULE.card_specs(XML), {"t6": [1]}, ALIGNMENT,
                                         tts=True, speech_ref="tone1")
        self.assertIn('draft.select("#t6").appendXml(', text)
        self.assertIn("<speech ref=\\\"tone1\\\"></speech>", text)

    def test_tts_requires_speech_ref(self):
        with self.assertRaises(ValueError):
            MODULE.build_selection(MODULE.card_specs(XML), {"t6": [1]}, ALIGNMENT, tts=True)

    def test_no_alignment_is_an_error(self):
        with self.assertRaises(ValueError):
            MODULE.build_selection(MODULE.card_specs(XML), {}, ALIGNMENT)


class ToneRefTests(unittest.TestCase):
    def test_reads_existing_tone_refs(self):
        folder = scratch("tone-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        path = folder / "resource_map.json"
        path.write_text(json.dumps([
            {"asset_id": "text1", "metadata": {"tone_ref": "7481554487442674186"}},
            {"asset_id": "text2", "metadata": {"tone_ref": "7481554487442674186"}},
            {"asset_id": "video1", "metadata": {"duration_us": 17600000}},
        ]), encoding="utf-8")
        self.assertEqual(MODULE.tone_refs(path), ["7481554487442674186"])

    def test_missing_file_returns_empty(self):
        folder = scratch("tone-empty-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        self.assertEqual(MODULE.tone_refs(folder / "nope.json"), [])


class NormalizeWorkspaceTests(unittest.TestCase):
    def test_normalizes_font_and_main_range(self):
        folder = scratch("ws-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        (folder / "target_draft.xml").write_text(XML, encoding="utf-8")
        (folder / "current_draft.xml").write_text(XML, encoding="utf-8")
        (folder / "resource_map.json").write_text(json.dumps([
            {"asset_id": "video1", "metadata": {"duration_us": 17600000}},
        ]), encoding="utf-8")
        report = MODULE.normalize_workspace(folder)
        self.assertTrue(report["target_draft.xml"]["changed"])
        updated = (folder / "target_draft.xml").read_text(encoding="utf-8")
        self.assertNotIn("font_ref", updated)
        self.assertIn('id="v2_b2"', updated)
        self.assertEqual(report["target_draft.xml"]["main_splits"][0]["segment"], "v2")
        self.assertEqual(updated, (folder / "current_draft.xml").read_text(encoding="utf-8"))


class WorkingCopyTests(unittest.TestCase):
    def test_rejects_draft_outside_root(self):
        root = scratch("root-")
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        outside = scratch("other-")
        self.addCleanup(lambda: shutil.rmtree(outside, ignore_errors=True))
        with self.assertRaises(ValueError):
            MODULE.working_copy(outside, root, "copy")

    def test_copies_into_root_with_ascii_name(self):
        folder = scratch("copy-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        root = folder / "drafts"
        source = root / "source"
        source.mkdir(parents=True)
        (source / "draft_content.json").write_bytes(b"payload")
        target = MODULE.working_copy(source, root, "headless")
        self.assertEqual(target.parent, root)
        self.assertTrue(target.name.isascii())
        self.assertEqual((target / "draft_content.json").read_bytes(), b"payload")


class SubtitleCueTests(unittest.TestCase):
    def test_existing_windows_reads_subtitles_only(self):
        windows = MODULE.existing_subtitle_windows(XML)
        self.assertEqual(windows, [(0, 866)])

    def test_fit_pushes_conflicting_cue_behind_blocked_window(self):
        # 与已有字幕重叠的句子被裁剪到遮挡之后，只要仍够长就保留。
        cues = [{"id": "a", "text": "甲", "start_ms": 0, "end_ms": 2820},
                {"id": "b", "text": "乙", "start_ms": 6080, "end_ms": 8300}]
        fitted = MODULE.fit_subtitle_cues(cues, [(0, 866)])
        self.assertEqual([cue["id"] for cue in fitted], ["a", "b"])
        self.assertEqual(fitted[0]["start_ms"], 866)

    def test_fit_drops_cue_fully_covered(self):
        cues = [{"id": "a", "text": "甲", "start_ms": 0, "end_ms": 800}]
        self.assertEqual(MODULE.fit_subtitle_cues(cues, [(0, 866)]), [])

    def test_fit_pushes_start_past_blocked_window(self):
        cues = [{"id": "a", "text": "甲", "start_ms": 6000, "end_ms": 8300}]
        fitted = MODULE.fit_subtitle_cues(cues, [(5433, 6433)])
        self.assertEqual(fitted[0]["start_ms"], 6433)
        self.assertEqual(fitted[0]["end_ms"], 8300)

    def test_fit_removes_overlap_between_cues(self):
        cues = [{"id": "a", "text": "甲", "start_ms": 0, "end_ms": 1000},
                {"id": "b", "text": "乙", "start_ms": 900, "end_ms": 2000}]
        fitted = MODULE.fit_subtitle_cues(cues, [])
        self.assertEqual([(cue["start_ms"], cue["end_ms"]) for cue in fitted],
                         [(0, 1000), (1000, 2000)])

    def test_selection_appends_subtitles_and_applies(self):
        text = MODULE.lyric_subtitle_selection([{"id": "a", "text": "甲<&", "start_ms": 0,
                                                 "end_ms": 1000}])
        self.assertIn('draft.select("multi").appendXml(', text)
        self.assertIn("甲&lt;&amp;", text)
        self.assertIn('start=\\"0\\" duration=\\"1000\\"', text)
        self.assertTrue(text.rstrip().endswith("draft.apply();"))



class MirrorSyncTests(unittest.TestCase):
    def test_syncs_root_mirrors_from_timelines(self):
        folder = scratch("mirror-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        timeline_dir = folder / "Timelines" / "E1C00739"
        timeline_dir.mkdir(parents=True)
        fresh = timeline_dir / "draft_content.json"
        fresh.write_bytes(b"fresh-timeline")
        (folder / "draft_content.json").write_bytes(b"stale")
        (folder / "template-2.tmp").write_bytes(b"stale")
        (timeline_dir / "template-2.tmp").write_bytes(b"stale")
        report = MODULE.sync_draft_mirrors(folder)
        self.assertEqual(Path(report["source"]), fresh)
        for name in ("draft_content.json", "template-2.tmp"):
            self.assertEqual((folder / name).read_bytes(), b"fresh-timeline")
        self.assertEqual((timeline_dir / "template-2.tmp").read_bytes(), b"fresh-timeline")

    def test_requires_timeline_file(self):
        folder = scratch("mirror-empty-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        with self.assertRaises(ValueError):
            MODULE.sync_draft_mirrors(folder)


class TemplateResourceTests(unittest.TestCase):
    def test_reports_missing_content_json(self):
        folder = scratch("resource-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        missing_dir = folder / "cache" / "template-b"
        missing_dir.mkdir(parents=True)
        (missing_dir / "config.json").write_text("{}", encoding="utf-8")
        complete_dir = folder / "cache" / "template-a"
        complete_dir.mkdir(parents=True)
        (complete_dir / "content.json").write_text("{}", encoding="utf-8")

        import sys as _sys
        _sys.path.insert(0, str(ROOT / "engine"))
        import windows_runtime as wr
        timeline = {"materials": {"text_templates": [
            {"resource_id": "a", "name": "完整", "path": complete_dir.as_posix()},
            {"resource_id": "b", "name": "缺资源", "path": missing_dir.as_posix()},
        ]}}
        original = wr._decrypt_metadata_in_memory
        wr._decrypt_metadata_in_memory = lambda path: timeline
        self.addCleanup(lambda: setattr(wr, "_decrypt_metadata_in_memory", original))

        report = MODULE.template_resource_report(folder)
        self.assertFalse(report["complete"])
        self.assertEqual([row["resource_id"] for row in report["missing_content_json"]], ["b"])


class TemplateCardTests(unittest.TestCase):
    def test_builds_one_card_per_cue_with_template_ref(self):
        cues = [{"id": "a", "text": "甲<&", "start_ms": 6433, "end_ms": 8300},
                {"id": "b", "text": "乙", "start_ms": 8300, "end_ms": 10460}]
        text = MODULE.lyric_template_selection(cues, "subtitle_template1")
        self.assertIn('<template ref=\\"subtitle_template1\\">', text)
        self.assertIn("甲&lt;&amp;", text)
        self.assertEqual(text.count("appendXml"), 2)
        self.assertTrue(text.rstrip().endswith("draft.apply();"))

    def test_rejects_empty_cues(self):
        with self.assertRaises(ValueError):
            MODULE.lyric_template_selection([], "subtitle_template1")

    def test_usable_assets_filters_broken_resources(self):
        assets = [
            {"asset_id": "a", "title": "可用", "metadata": {"text_template_slots": "[{}]"}},
            {"asset_id": "b", "title": "损坏",
             "metadata": {"text_template_slots_error": "text template resource has no readable content.json"}},
            {"asset_id": "c", "title": "无槽位", "metadata": {}},
        ]
        usable = MODULE.usable_template_assets(assets)
        self.assertEqual([asset["asset_id"] for asset in usable], ["a"])


class LyricStyleTests(unittest.TestCase):
    def test_extract_reads_lyric_animation_style(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "engine"))
        import lyrics_style as style_module
        import windows_runtime as wr

        folder = scratch("style-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        cache = folder / "cache" / "res-1"
        cache.mkdir(parents=True)
        (cache / "LyricStyle.json").write_text(json.dumps({
            "title": "layout_spread",
            "text_style": {"font_id": ["7068531367386026526"], "font_size": 12,
                           "global_italic": True, "line_spacing": 0.5,
                           "text_color": ["#FFFFFF", "#fd629e"], "text_color_random": 1},
            "animations": {"duration_ratio": [0.08, 0.76, 0.08], "max_dur": 1.5, "min_dur": 0.15},
        }), encoding="utf-8")
        timeline = {"materials": {"text_templates": [{
            "is_lyric_effect": True, "name": "浪漫氛围", "resource_id": "7591420714515844395",
            "path": cache.as_posix(),
            "resources": [{"panel": "fonts", "path": "C:/fonts/猫啃网烟波宋-B.ttf"}]}]}}
        original = wr._decrypt_metadata_in_memory
        wr._decrypt_metadata_in_memory = lambda path: timeline
        self.addCleanup(lambda: setattr(wr, "_decrypt_metadata_in_memory", original))

        style = style_module.extract(folder)
        self.assertEqual(style["template_name"], "浪漫氛围")
        self.assertEqual(style["font_size"], 12)
        self.assertTrue(style["italic"])
        self.assertEqual(style["colors"], ["#FFFFFF", "#fd629e"])
        self.assertEqual(style["layout_title"], "layout_spread")

    def test_color_for_is_deterministic(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "engine"))
        import lyrics_style as style_module
        style = {"colors": ["#FFFFFF", "#fd629e"], "color_random": True}
        self.assertEqual(style_module.color_for(style, 0), "#FFFFFF")
        self.assertEqual(style_module.color_for(style, 1), "#fd629e")
        self.assertEqual(style_module.color_for(style, 2), "#FFFFFF")
        fixed = {"colors": ["#000000"], "color_random": True}
        self.assertEqual(style_module.color_for(fixed, 5), "#000000")


class SubtitleColorTests(unittest.TestCase):
    def test_selection_uses_per_cue_colors(self):
        cues = [{"id": "a", "text": "甲", "start_ms": 0, "end_ms": 500},
                {"id": "b", "text": "乙", "start_ms": 600, "end_ms": 1100}]
        text = MODULE.lyric_subtitle_selection(cues, colors=["#FFFFFF", "#fd629e"])
        self.assertIn('color=\\"#FFFFFF\\"', text)
        self.assertIn('color=\\"#fd629e\\"', text)


class OfficialLyricsTests(unittest.TestCase):
    """official 分支：整组语义、零落地必须失败、报告字段完整。

    这些路径此前零覆盖，而它们决定"看起来跑通了但成片没有歌词动效"会不会重现。
    """

    def setUp(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "engine"))
        import draftediting_runtime as runtime
        import lyra_cli as cli

        self.runtime, self.cli = runtime, cli
        self.synced = []
        self.updates = []
        self.views = []
        self.original = (runtime.blueprint_sync, cli.load_workspace_views,
                         cli.lyrics_animation_update)

        runtime.blueprint_sync = lambda *a, **k: self.synced.append(a)
        cli.load_workspace_views = lambda ws: self.views.pop(0) if self.views else ("", {})
        cli.lyrics_animation_update = self._update
        self.addCleanup(self._restore)

    def _restore(self):
        (self.runtime.blueprint_sync, self.cli.load_workspace_views,
         self.cli.lyrics_animation_update) = self.original

    def _update(self, draft_root, ref, seg_id, resource, **kwargs):
        self.updates.append((seg_id, resource))
        return {}

    @staticmethod
    def _xml(rows):
        parts = []
        for xml_id, text, has_template in rows:
            template = '<template ref="t1" />' if has_template else ""
            parts.append(f'<text id="{xml_id}">{template}'
                         f'<content><sub text="{text}" /></content></text>')
        return "<draft>" + "".join(parts) + "</draft>"

    def test_one_update_covers_whole_group(self):
        # 实测语义：一次 update 作用于整组。判据是「只发一次 update 命令、且复核后没有
        # leftover」——第 2 轮只是复核确认，所以 rounds 会是 2，不作为判据。
        first = self._xml([("t12", "九月不必再逢", False), ("t13", "于是不觉可闻", False)])
        after = self._xml([("t12", "九月不必再逢", True), ("t13", "于是不觉可闻", True)])
        self.views = [(first, {"t12": "u12", "t13": "u13"}), (after, {})]
        report = MODULE.official_apply_animation("/ws", "local://d", "/root", "vimo://7",
                                                ["九月不必再逢", "于是不觉可闻"])
        self.assertEqual(len(self.updates), 1, "整组语义下不应逐句发命令")
        self.assertEqual(report["applied"], ["九月不必再逢"])
        self.assertEqual(report["leftover"], [])
        self.assertLessEqual(report["rounds"], 2)

    def test_reports_leftover_when_not_all_landed(self):
        first = self._xml([("t12", "九月不必再逢", False), ("t13", "于是不觉可闻", False)])
        still = self._xml([("t12", "九月不必再逢", True), ("t13", "于是不觉可闻", False)])
        self.views = [(first, {"t12": "u12", "t13": "u13"}), (still, {"t13": "u13b"}),
                      (still, {"t13": "u13b"})]
        report = MODULE.official_apply_animation("/ws", "local://d", "/root", "vimo://7",
                                                ["九月不必再逢", "于是不觉可闻"],
                                                max_rounds=2)
        self.assertGreater(report["leftover_count"], 0)
        self.assertIn("于是不觉可闻", report["leftover"])

    def test_records_failures_and_does_not_loop_forever(self):
        xml = self._xml([("t12", "九月不必再逢", False)])
        self.views = [(xml, {"t12": "u12"})] * 4

        def boom(*args, **kwargs):
            raise RuntimeError("official rejected: expected one of: segment_text")

        self.cli.lyrics_animation_update = boom
        report = MODULE.official_apply_animation("/ws", "local://d", "/root", "vimo://7",
                                                ["九月不必再逢"], max_rounds=3)
        self.assertEqual(report["applied_count"], 0)
        self.assertEqual(report["failed_count"], 1)
        self.assertIn("segment_text", report["failed"][0]["error"])

    def test_parse_segment_rows_is_element_based(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "engine"))
        import lyra_cli as cli

        rows = cli.parse_segment_rows(
            '<draft><text id="t12" class="segment_text">\n'
            '<content><sub text="九月不必再逢" /></content></text>\n'
            '<template_package id="p1"><template ref="x" /></template_package></draft>')
        self.assertEqual(rows, [("t12", "九月不必再逢", False)])

        wrapped = cli.parse_segment_rows(
            '<draft><text\n  id="t7"\n  class="segment_text">'
            '<content><sub text="于是不觉可闻" /></content></text></draft>')
        self.assertEqual(wrapped, [("t7", "于是不觉可闻", False)])

        inline = cli.parse_segment_rows(
            '<draft><text id="t8"><content><sub text="abc" /></content></text></draft>')
        self.assertEqual(inline, [("t8", "abc", False)])

        applied = cli.parse_segment_rows(
            '<draft><text id="t9"><template ref="tpl" />'
            '<content><sub text="abc" /></content></text></draft>')
        self.assertEqual(applied, [("t9", "abc", True)])

    def test_pending_ignores_subtitle_segments(self):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "engine"))
        import lyra_cli as cli

        xml = ('<draft><subtitle id="t1"><content><sub text="九月不必再逢" /></content>'
               '</subtitle><text id="t12"><content><sub text="九月不必再逢" /></content>'
               '</text></draft>')
        pending = cli.pending_lyric_segments(xml, {"t1": "u1", "t12": "u12"},
                                             ["九月不必再逢"])
        # 官方 update 只接受 segment_text，<subtitle> 送进去必然失败
        self.assertEqual(pending, [("t12", "u12", "九月不必再逢")])


if __name__ == "__main__":
    unittest.main()
