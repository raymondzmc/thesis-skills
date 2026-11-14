import contextlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "thesis-kit", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import render_pages  # noqa: E402
from handmade_pdf import write_pdf  # noqa: E402

SCRIPT = os.path.join(SCRIPTS, "render_pages.py")

HAVE_POPPLER = bool(shutil.which("pdftoppm") and shutil.which("pdfinfo"))


def png_size(path):
    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("%s is not a PNG file" % path)
    return struct.unpack(">II", head[16:24])


class ParsePagesTest(unittest.TestCase):
    def test_accepts_single_pages_ranges_and_lists(self):
        cases = {
            "3": [3],
            "3-5": [3, 4, 5],
            "3,7,9-10": [3, 7, 9, 10],
            " 2 , 4 - 5 ": [2, 4, 5],
            "5,3-4,5": [5, 3, 4],
        }
        for spec, want in cases.items():
            with self.subTest(spec=spec):
                self.assertEqual(render_pages.parse_pages(spec), want)

    def test_rejects_zero_reversed_negative_and_malformed_specs(self):
        for spec in ["", "0", "2-0", "5-3", "-2", "3-", "a", "1,,2", "1.5"]:
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    render_pages.parse_pages(spec)


class ParseCropTest(unittest.TestCase):
    def test_parses_four_page_fractions(self):
        self.assertEqual(render_pages.parse_crop("0,0.5,1,0.5"), (0.0, 0.5, 1.0, 0.5))
        self.assertEqual(
            render_pages.parse_crop(" .1, 0.2 ,0.3,0.4 "), (0.1, 0.2, 0.3, 0.4)
        )

    def test_rejects_crops_that_are_malformed_empty_or_off_the_page(self):
        bad = [
            "0,0.5,1",  # three values
            "a,b,c,d",
            "nan,0,0.5,0.5",
            "-0.1,0,1,1",  # starts left of the page
            "0,0,0,1",  # zero width
            "0,0,1,0",  # zero height
            "0.5,0,0.6,1",  # runs off the right edge
            "0,0.6,1,0.5",  # runs off the bottom edge
            "0,0,1.5,1",
        ]
        for spec in bad:
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    render_pages.parse_crop(spec)


class CropPixelsTest(unittest.TestCase):
    def test_converts_page_fractions_to_pixels_covering_the_region(self):
        cases = [
            # (page width pts, page height pts, dpi, crop) -> (x, y, W, H)
            ((612, 792, 150, (0, 0.5, 1, 0.5)), (0, 825, 1275, 825)),
            ((595.276, 841.89, 100, (0.1, 0.2, 0.3, 0.4)), (82, 233, 249, 469)),
            # the whole page is pdftoppm's rounded-up page size
            ((595.276, 841.89, 100, (0, 0, 1, 1)), (0, 0, 827, 1170)),
            # float noise just past the edge does not add a pixel column
            ((612, 792, 72, (0, 0, 1 + 1e-12, 1)), (0, 0, 612, 792)),
        ]
        for args, want in cases:
            with self.subTest(args=args):
                self.assertEqual(render_pages.crop_pixels(*args), want)


class ParsePdfinfoTest(unittest.TestCase):
    def test_reads_page_count_and_displayed_page_sizes(self):
        text = (
            "Title:           Something\n"
            "Pages:           3\n"
            "Encrypted:       no\n"
            "Page    1 size:  612 x 792 pts (letter)\n"
            "Page    1 rot:   0\n"
            "Page    2 size:  595.276 x 841.89 pts (A4)\n"
            "Page    2 rot:   90\n"
            "Page    3 size:  300 x 400 pts\n"
            "Page    3 rot:   270\n"
        )
        count, sizes = render_pages.parse_pdfinfo(text)
        self.assertEqual(count, 3)
        self.assertEqual(
            sizes, {1: (612.0, 792.0), 2: (841.89, 595.276), 3: (400.0, 300.0)}
        )


@unittest.skipUnless(HAVE_POPPLER, "pdftoppm/pdfinfo (Poppler) not installed")
class RenderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.out_dir = os.path.join(self.tmp, "pages")
        # page 2 has its own size, so its image proves which page was drawn
        self.pdf = write_pdf(
            os.path.join(self.tmp, "paper.pdf"),
            [["Page one"], ["Accuracy improves from 0.671 to 0.727."]],
            page_sizes=[(612, 792), (400, 300)],
        )

    def run_main(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = render_pages.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_renders_the_requested_page_to_a_named_png(self):
        code, out, _ = self.run_main(
            self.pdf, "--pages", "2", "--dpi", "72", "--out", self.out_dir
        )
        self.assertEqual(code, 0)
        expected = os.path.join(self.out_dir, "paper-p2.png")
        self.assertEqual(out.splitlines(), [expected])
        self.assertEqual(png_size(expected), (400, 300))
        self.assertEqual(os.listdir(self.out_dir), ["paper-p2.png"])

    def test_json_lists_each_rendered_page_and_its_path(self):
        code, out, _ = self.run_main(
            self.pdf, "--pages", "2,1", "--dpi", "72", "--out", self.out_dir, "--json"
        )
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(
            report["images"],
            [
                {"page": 2, "path": os.path.join(self.out_dir, "paper-p2.png")},
                {"page": 1, "path": os.path.join(self.out_dir, "paper-p1.png")},
            ],
        )
        self.assertEqual(report["dpi"], 72)
        self.assertIsNone(report["crop"])
        for image in report["images"]:
            self.assertTrue(os.path.isfile(image["path"]))

    def test_crop_renders_the_requested_fraction_of_the_page(self):
        code, out, _ = self.run_main(
            self.pdf, "--pages", "2", "--dpi", "72", "--out", self.out_dir,
            "--crop", "0,0.5,1,0.5",
        )
        self.assertEqual(code, 0)
        expected = os.path.join(self.out_dir, "paper-p2-crop.png")
        self.assertEqual(out.splitlines(), [expected])
        self.assertEqual(png_size(expected), (400, 150))

    def test_renders_the_visible_crop_box_that_pdfinfo_reports(self):
        pdf = write_pdf(
            os.path.join(self.tmp, "boxed.pdf"), [["Inside the crop box"]],
            cropbox=[0, 0, 300, 400],
        )
        code, out, _ = self.run_main(
            pdf, "--pages", "1", "--dpi", "72", "--out", self.out_dir
        )
        self.assertEqual(code, 0)
        self.assertEqual(png_size(out.strip()), (300, 400))

    def test_page_past_the_end_exits_2_before_rendering_anything(self):
        code, out, err = self.run_main(
            self.pdf, "--pages", "1-3", "--dpi", "72", "--out", self.out_dir
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("page 3", err)
        self.assertIn("2 pages", err)
        self.assertFalse(os.path.exists(self.out_dir) and os.listdir(self.out_dir))

    def test_unreadable_pdf_exits_2_with_poppler_message(self):
        fake = os.path.join(self.tmp, "fake.pdf")
        with open(fake, "w") as handle:
            handle.write("this is not a PDF\n")
        code, out, err = self.run_main(fake, "--pages", "1", "--out", self.out_dir)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("pdfinfo failed", err)


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def exit_code(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = render_pages.main(list(args))
        except SystemExit as exc:
            code = exc.code
        return code, stderr.getvalue()

    def test_bad_arguments_exit_2_with_a_message(self):
        pdf = write_pdf(os.path.join(self.tmp, "paper.pdf"), [["Page one"]])
        out = os.path.join(self.tmp, "pages")
        cases = {
            "page zero": [pdf, "--pages", "0", "--out", out],
            "crop off the page": [pdf, "--pages", "1", "--crop", "0,0,2,1", "--out", out],
            "zero dpi": [pdf, "--pages", "1", "--dpi", "0", "--out", out],
            "missing pdf": [os.path.join(self.tmp, "nope.pdf"), "--pages", "1", "--out", out],
        }
        for name, args in cases.items():
            with self.subTest(name):
                code, err = self.exit_code(*args)
                self.assertEqual(code, 2)
                self.assertNotIn("Traceback", err)
                self.assertTrue(err.strip(), "expected an error message")
        self.assertFalse(os.path.exists(out))

    def test_missing_poppler_exits_2_and_says_how_to_install_it(self):
        pdf = write_pdf(os.path.join(self.tmp, "paper.pdf"), [["Page one"]])
        empty_bin = os.path.join(self.tmp, "bin")
        os.mkdir(empty_bin)
        result = subprocess.run(
            [sys.executable, SCRIPT, pdf, "--pages", "1",
             "--out", os.path.join(self.tmp, "pages")],
            capture_output=True, text=True, env=dict(os.environ, PATH=empty_bin),
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("pdftoppm", result.stderr)
        self.assertIn("brew install poppler", result.stderr)
        self.assertIn("apt install poppler-utils", result.stderr)


if __name__ == "__main__":
    unittest.main()
