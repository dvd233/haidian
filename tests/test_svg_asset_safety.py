from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.symlink_test_support import symlink_or_skip

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from svg_asset_safety import visual_svg_asset_issues  # noqa: E402


SVG_NS = "http://www.w3.org/2000/svg"


def write_svg(root: Path, content: str | bytes, name: str = "icon.svg") -> Path:
    submission = root / "submissions" / "alice" / "svg-package"
    asset = submission / "visual" / "assets" / name
    asset.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        asset.write_bytes(content)
    else:
        asset.write_text(content, encoding="utf-8")
    return submission


class SvgAssetSafetyTests(unittest.TestCase):
    def test_local_references_and_unsafe_text_inside_comments_are_allowed(self) -> None:
        content = f"""<svg xmlns="{SVG_NS}" viewBox="0 0 10 10">
<!-- <!DOCTYPE svg><script>comment only</script> -->
<defs><linearGradient id="paint"><stop offset="1"/></linearGradient></defs>
<style>.shape {{ fill: url(#paint); }} .texture {{ fill: url(icons/pattern.svg#tile); }}</style>
<rect class="shape" width="10" height="10"/>
<use href="#paint"/><image href="icons/local.png"/>
</svg>"""
        with tempfile.TemporaryDirectory() as tmp:
            submission = write_svg(Path(tmp), content)
            self.assertEqual(visual_svg_asset_issues(submission), [])

    def test_active_container_elements_are_rejected_namespace_independently(self) -> None:
        for element in [
            "script",
            "foreignObject",
            "iframe",
            "object",
            "embed",
            "handler",
            "listener",
            "link",
            "audio",
            "video",
            "animate",
            "animateMotion",
            "animateTransform",
            "set",
            "discard",
        ]:
            with self.subTest(element=element), tempfile.TemporaryDirectory() as tmp:
                content = f'<svg xmlns="{SVG_NS}"><{element}/></svg>'
                submission = write_svg(Path(tmp), content)
                messages = [message for _, message in visual_svg_asset_issues(submission)]
                self.assertIn(f"SVG must not contain <{element.casefold()}> elements", messages)

    def test_event_handlers_and_external_or_active_uris_are_rejected(self) -> None:
        cases = [
            f'<svg xmlns="{SVG_NS}" onload="run()"/>',
            f'<svg xmlns="{SVG_NS}"><image href="https://example.com/a.png"/></svg>',
            f'<svg xmlns="{SVG_NS}"><image href="//example.com/a.png"/></svg>',
            f'<svg xmlns="{SVG_NS}"><image href="data:image/png;base64,AA=="/></svg>',
            f'<svg xmlns="{SVG_NS}"><a href="java&#x0A;script:run()"/></svg>',
            f'<svg xmlns="{SVG_NS}"><image href="/outside-package.svg"/></svg>',
            f'<svg xmlns="{SVG_NS}"><image href="icons\\outside.svg"/></svg>',
            f'<svg xmlns="{SVG_NS}"><image href="icons/%252e%252e/outside.svg"/></svg>',
            (
                f'<svg xmlns="{SVG_NS}" xmlns:xlink="http://www.w3.org/1999/xlink">'
                '<use xlink:href="file:///tmp/item.svg"/></svg>'
            ),
        ]
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                submission = write_svg(Path(tmp), content)
                self.assertTrue(visual_svg_asset_issues(submission))

    def test_css_urls_and_imports_are_checked_in_attributes_and_style_elements(self) -> None:
        cases = [
            f'<svg xmlns="{SVG_NS}"><rect style="fill:url(https://example.com/a.svg)"/></svg>',
            f'<svg xmlns="{SVG_NS}"><style>@import "//example.com/a.css";</style></svg>',
            f'<svg xmlns="{SVG_NS}"><rect fill="url(j\\61vascript:run())"/></svg>',
        ]
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                submission = write_svg(Path(tmp), content)
                messages = [message for _, message in visual_svg_asset_issues(submission)]
                self.assertIn(
                    "SVG CSS must not load external, data, or script resources",
                    messages,
                )

    def test_doctype_entities_and_processing_instructions_are_rejected(self) -> None:
        cases = [
            f'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="{SVG_NS}">&x;</svg>',
            f'<?xml-stylesheet href="https://example.com/a.css"?><svg xmlns="{SVG_NS}"/>',
        ]
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                submission = write_svg(Path(tmp), content)
                self.assertTrue(visual_svg_asset_issues(submission))

    def test_encoding_xml_shape_and_root_element_are_validated(self) -> None:
        cases = [
            (b"\xff\xfe", "SVG assets must be UTF-8 text"),
            (f'<svg xmlns="{SVG_NS}"><path></svg>', "SVG must be well-formed XML"),
            ("<html/>", "SVG root element must be <svg>"),
            ("<svg/>", "SVG root element must use the SVG namespace"),
            (
                f'<?xml version="1.0" encoding="ISO-8859-1"?><svg xmlns="{SVG_NS}"/>',
                "SVG XML declarations must specify UTF-8 encoding",
            ),
        ]
        for content, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                submission = write_svg(Path(tmp), content)
                messages = [message for _, message in visual_svg_asset_issues(submission)]
                self.assertTrue(any(message.startswith(expected) for message in messages), messages)

    def test_utf8_bom_and_utf8_xml_declaration_are_allowed(self) -> None:
        content = f'<?xml version="1.0" encoding="UTF-8"?><svg xmlns="{SVG_NS}"/>'.encode()
        with tempfile.TemporaryDirectory() as tmp:
            submission = write_svg(Path(tmp), b"\xef\xbb\xbf" + content)
            self.assertEqual([], visual_svg_asset_issues(submission))

    def test_svg_reads_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            submission = write_svg(Path(tmp), f'<svg xmlns="{SVG_NS}"/>')
            with mock.patch("svg_asset_safety.MAX_SVG_BYTES", 4):
                messages = [message for _, message in visual_svg_asset_issues(submission)]
            self.assertIn("SVG assets must be <= 4 bytes", messages)

    def test_foreign_namespace_elements_and_xml_base_are_rejected(self) -> None:
        cases = [
            f'<svg xmlns="{SVG_NS}" xmlns:h="urn:other"><h:section/></svg>',
            f'<svg xmlns="{SVG_NS}" xml:base="images/"/>',
        ]
        for content in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                submission = write_svg(Path(tmp), content)
                self.assertTrue(visual_svg_asset_issues(submission))

    def test_nested_and_undeclared_assets_are_discovered_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            submission = write_svg(
                Path(tmp),
                f'<svg xmlns="{SVG_NS}"><script/></svg>',
                "nested/undeclared.SVG",
            )
            issues = visual_svg_asset_issues(submission)
            self.assertEqual(issues[0][0], "visual/assets/nested/undeclared.SVG")

    def test_svg_symlinks_are_rejected_without_following_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            submission = write_svg(root, f'<svg xmlns="{SVG_NS}"/>', "real.svg")
            linked = submission / "visual" / "assets" / "linked.svg"
            symlink_or_skip(self, linked, root / "outside.svg")
            issues = visual_svg_asset_issues(submission)
            self.assertIn(
                ("visual/assets/linked.svg", "visual SVG asset paths must not use symbolic links"),
                issues,
            )

    def test_symlinked_asset_directories_are_rejected_without_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            submission = write_svg(root, f'<svg xmlns="{SVG_NS}"/>', "real.svg")
            outside = root / "outside"
            outside.mkdir()
            (outside / "active.svg").write_text(
                f'<svg xmlns="{SVG_NS}"><script/></svg>', encoding="utf-8"
            )
            linked = submission / "visual" / "assets" / "linked"
            symlink_or_skip(self, linked, outside, target_is_directory=True)
            issues = visual_svg_asset_issues(submission)
            self.assertIn(
                ("visual/assets/linked", "visual SVG asset paths must not use symbolic links"),
                issues,
            )


if __name__ == "__main__":
    unittest.main()
