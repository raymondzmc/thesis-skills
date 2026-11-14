"""Test helper: build tiny, valid PDF files by hand (no PDF library needed).

Each page holds lines of Helvetica text, which Poppler can extract with
pdftotext and render with pdftoppm. Used by the tests of paper_text,
check_numbers and render_pages.
"""

SAMPLE_LINE = "Accuracy improves from 0.671 to 0.727 on 1,000 documents (12.5%)."


def _pdf_string(text):
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return "(" + escaped + ")"


def build_pdf(pages, title=None, size=(612, 792), cropbox=None, rotate=None,
              page_sizes=None):
    """Return the bytes of a PDF with one page per item of `pages`.

    pages: list of pages, each a list of text lines.
    title: optional /Title for the document information dictionary.
    size: MediaBox width and height in points.
    page_sizes: optional list of per-page (width, height), overriding size.
    cropbox: optional [x0, y0, x1, y1] CropBox applied to every page.
    rotate: optional /Rotate value (0, 90, 180, 270) for every page.
    """
    first_page = 4  # objects 1-3: catalog, page tree, font
    kids = " ".join("%d 0 R" % (first_page + 2 * i) for i in range(len(pages)))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages)),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
        " /Encoding /WinAnsiEncoding >>",
    ]
    for i, lines in enumerate(pages):
        width, height = page_sizes[i] if page_sizes else size
        extra = ""
        if cropbox is not None:
            extra += " /CropBox [%s]" % " ".join(str(v) for v in cropbox)
        if rotate is not None:
            extra += " /Rotate %d" % rotate
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s]%s"
            " /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
            % (width, height, extra, first_page + 2 * i + 1)
        )
        ops = ["BT", "/F1 12 Tf", "14 TL", "72 %s Td" % (height - 72)]
        ops += [_pdf_string(line) + " Tj T*" for line in lines]
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects.append(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )
    info = None
    if title is not None:
        objects.append("<< /Title %s >>" % _pdf_string(title))
        info = len(objects)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        if isinstance(body, str):
            body = body.encode("latin-1")
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    trailer = "<< /Size %d /Root 1 0 R" % (len(objects) + 1)
    if info is not None:
        trailer += " /Info %d 0 R" % info
    trailer += " >>"
    out += b"trailer\n" + trailer.encode("latin-1")
    out += b"\nstartxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


def write_pdf(path, pages, **kwargs):
    """Write build_pdf(pages, **kwargs) to `path` and return the path."""
    with open(path, "wb") as handle:
        handle.write(build_pdf(pages, **kwargs))
    return path
