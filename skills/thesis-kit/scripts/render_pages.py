#!/usr/bin/env python3
"""Render pages, or parts of pages, of a PDF as PNG images.

Lets an agent look at a table, an equation or a figure caption in the
original paper (for example to check a re-typeset table against it) or in
the compiled thesis.

Usage:
    python3 render_pages.py PDF --pages SPEC [--dpi 150] [--out DIR]
                            [--crop LEFT,TOP,WIDTH,HEIGHT] [--json]

    SPEC is 1-based: "3", "3-5" or "3,7,9-10".
    --crop takes fractions of the page measured from its top-left corner:
    "0,0.5,1,0.5" is the bottom half, "0,0,0.5,1" the left column.

Page P is written to DIR/<pdfstem>-p<P>.png, or DIR/<pdfstem>-p<P>-crop.png
with --crop (DIR defaults to thesis-work/pages; existing images are overwritten). The
PNG paths are printed one per line; --json prints a report instead. Pages
are drawn as a PDF viewer shows them: the crop box, with the page rotation
applied.

Needs pdftoppm and pdfinfo from Poppler (`brew install poppler` on macOS,
`apt install poppler-utils` on Debian/Ubuntu).

--find PHRASE prints, one per line, the physical pages (1-based, as --pages
counts them) whose text contains PHRASE, ignoring case and spacing, and
renders nothing. Use it to locate a page before rendering it: page numbers
in a LaTeX log are printed labels (roman front matter, restarts), not PDF
pages.

Exit codes: 0 rendered (or, with --find, the phrase was found); 1 with
--find, the phrase is on no page; 2 bad arguments, a page out of range, an
unreadable PDF, or Poppler missing.

Example:
    python3 render_pages.py papers/smith2021.pdf --pages 6 --crop 0,0.5,1,0.5
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

INSTALL_HINT = (
    "Install Poppler: `brew install poppler` on macOS, "
    "`apt install poppler-utils` on Debian/Ubuntu."
)


def parse_pages(spec):
    """Parse a 1-based page spec such as "3", "3-5" or "3,7,9-10".

    Returns the pages in the order given, without duplicates. Raises
    ValueError for anything else (pages are numbered from 1).
    """
    pages = []
    for part in spec.split(","):
        part = part.strip()
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", part)
        if not match:
            raise ValueError(
                "bad page spec %r: use pages like 3, 3-5 or 3,7,9-10" % spec
            )
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        if first < 1:
            raise ValueError("bad page spec %r: pages start at 1" % spec)
        if last < first:
            raise ValueError("bad page spec %r: range %s is reversed" % (spec, part))
        for page in range(first, last + 1):
            if page not in pages:
                pages.append(page)
    return pages


def parse_crop(spec):
    """Parse "LEFT,TOP,WIDTH,HEIGHT" (fractions of the page) into floats.

    The origin is the top-left corner of the page; "0,0.5,1,0.5" is the
    bottom half. Raises ValueError unless the box is non-empty and lies on
    the page.
    """
    usage = "bad crop %r: use LEFT,TOP,WIDTH,HEIGHT as fractions 0-1" % spec
    parts = spec.split(",")
    if len(parts) != 4:
        raise ValueError(usage)
    try:
        left, top, width, height = (float(part) for part in parts)
    except ValueError:
        raise ValueError(usage)
    eps = 1e-9
    ok = (
        0 <= left < 1
        and 0 <= top < 1
        and 0 < width <= 1 + eps
        and 0 < height <= 1 + eps
        and left + width <= 1 + eps
        and top + height <= 1 + eps
    )
    if not ok:  # also catches NaN, for which every comparison is False
        raise ValueError(usage + " (the box must be non-empty and on the page)")
    return (left, top, width, height)


def crop_pixels(width_pts, height_pts, dpi, crop):
    """Return pdftoppm's (x, y, W, H) in pixels for a crop in page fractions.

    width_pts and height_pts are the page size as displayed (after any
    rotation). The pixel box covers the requested region: the top-left
    corner is rounded down, the bottom-right corner up, and the box is
    clipped to the rendered page, which pdftoppm rounds up to whole pixels.
    """
    left, top, width, height = crop
    tol = 1e-6  # absorbs float noise such as 0.30000000000000004
    page_w = width_pts * dpi / 72.0
    page_h = height_pts * dpi / 72.0
    max_w = math.ceil(page_w - tol)
    max_h = math.ceil(page_h - tol)
    x = math.floor(left * page_w + tol)
    y = math.floor(top * page_h + tol)
    right = min(math.ceil((left + width) * page_w - tol), max_w)
    bottom = min(math.ceil((top + height) * page_h - tol), max_h)
    return (x, y, max(right - x, 1), max(bottom - y, 1))


def parse_pdfinfo(text):
    """Parse `pdfinfo -f F -l L` output.

    Returns (page_count, {page: (width_pts, height_pts)}). pdfinfo reports
    the crop box before rotation, so pages rotated by 90 or 270 degrees have
    their width and height swapped to match the rendered image.
    """
    count = None
    sizes = {}
    rotations = {}
    for line in text.splitlines():
        match = re.match(r"Pages:\s+(\d+)", line)
        if match:
            count = int(match.group(1))
            continue
        match = re.match(r"Page\s+(\d+)\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", line)
        if match:
            sizes[int(match.group(1))] = (float(match.group(2)), float(match.group(3)))
            continue
        match = re.match(r"Page\s+(\d+)\s+rot:\s+(-?\d+)", line)
        if match:
            rotations[int(match.group(1))] = int(match.group(2)) % 360
    for page, rotation in rotations.items():
        if page in sizes and rotation in (90, 270):
            width, height = sizes[page]
            sizes[page] = (height, width)
    return count, sizes


def _error(message):
    print("render_pages: " + message, file=sys.stderr)


class ToolError(Exception):
    """A Poppler command failed."""


def _run(command):
    result = subprocess.run(command, capture_output=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ToolError("%s failed on %s: %s" % (command[0], command[-1], detail))
    return result.stdout


def _pdfinfo(pdf, first=None, last=None):
    command = ["pdfinfo"]
    if first is not None:
        command += ["-f", str(first), "-l", str(last)]
    return _run(command + [pdf])


def _arg_type(parse):
    """Turn a parser that raises ValueError into an argparse type."""
    def convert(value):
        try:
            return parse(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc))
    return convert


def _positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a whole number" % value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1, got %d" % number)
    return number


def find_pages(pdf, phrase):
    """Print the 1-based physical pages whose text contains phrase."""
    if not shutil.which("pdftotext"):
        _error("pdftotext not found on PATH. %s" % INSTALL_HINT)
        return 2
    try:
        text = _run(["pdftotext", "-layout", pdf, "-"])
    except ToolError as exc:
        _error(str(exc))
        return 2
    squash = lambda s: " ".join(s.lower().split())
    needle = squash(phrase)
    hits = [n for n, page in enumerate(text.split("\f"), 1) if needle in squash(page)]
    for n in hits:
        print(n)
    return 0 if hits else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pdf", metavar="PDF", help="the PDF file to render")
    parser.add_argument(
        "--pages", metavar="SPEC", type=_arg_type(parse_pages),
        help='1-based pages: "3", "3-5" or "3,7,9-10"',
    )
    parser.add_argument(
        "--find", metavar="PHRASE",
        help="print the physical pages whose text contains PHRASE and exit",
    )
    parser.add_argument(
        "--dpi", type=_positive_int, default=150, help="resolution (default: 150)"
    )
    parser.add_argument(
        "--out", default=os.path.join("thesis-work", "pages"), metavar="DIR",
        help="output directory (default: thesis-work/pages)",
    )
    parser.add_argument(
        "--crop", metavar="LEFT,TOP,WIDTH,HEIGHT", type=_arg_type(parse_crop),
        help="render only this box, in fractions of the page from its top-left "
        "corner (0,0.5,1,0.5 is the bottom half)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="print a JSON report instead of one PNG path per line",
    )
    args = parser.parse_args(argv)
    pages, crop = args.pages, args.crop
    if not pages and not args.find:
        parser.error("give --pages SPEC, or --find PHRASE to locate pages")

    if not os.path.isfile(args.pdf):
        _error("no such file: %s" % args.pdf)
        return 2
    if args.find:
        return find_pages(args.pdf, args.find)
    missing = [tool for tool in ("pdftoppm", "pdfinfo") if not shutil.which(tool)]
    if missing:
        _error("%s not found on PATH. %s" % (" and ".join(missing), INSTALL_HINT))
        return 2
    try:
        count, _ = parse_pdfinfo(_pdfinfo(args.pdf))
        beyond = [page for page in pages if page > count]
        if beyond:
            _error("page %d is out of range: %s has %d pages"
                   % (beyond[0], args.pdf, count))
            return 2
        sizes = {}
        if crop:
            _, sizes = parse_pdfinfo(_pdfinfo(args.pdf, min(pages), max(pages)))
        os.makedirs(args.out, exist_ok=True)
        stem = os.path.splitext(os.path.basename(args.pdf))[0]
        images = []
        for page in pages:
            prefix = os.path.join(args.out, "%s-p%d" % (stem, page))
            command = [
                "pdftoppm", "-png", "-r", str(args.dpi),
                "-f", str(page), "-l", str(page), "-singlefile",
                # the crop box is the page a viewer shows and the size pdfinfo
                # reports; pdftoppm would otherwise draw the larger media box
                "-cropbox",
            ]
            if crop:
                prefix += "-crop"
                width_pts, height_pts = sizes[page]
                x, y, w, h = crop_pixels(width_pts, height_pts, args.dpi, crop)
                command += ["-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h)]
            # -singlefile makes pdftoppm write exactly PREFIX.png
            _run(command + [args.pdf, prefix])
            images.append({"page": page, "path": prefix + ".png"})
    except ToolError as exc:
        _error(str(exc))
        return 2
    if args.json:
        report = {"pdf": args.pdf, "dpi": args.dpi,
                  "crop": list(crop) if crop else None, "images": images}
        print(json.dumps(report, indent=2))
    else:
        for image in images:
            print(image["path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
