# Reading the papers

The papers are the evidence. Every sentence a chapter states about a method or a result
has to trace to them, so read them carefully once and store what you read.

## Get the best source first

1. LaTeX source. Ask the student for it (Overleaf: Menu > Download > Source). For an
   arXiv paper, `https://arxiv.org/e-print/<id>` returns the source tarball; the student
   is the author, so this is personal use, but keep to one request every 3 seconds.
   Source gives exact tables, equations, figure files and `.bib` entries.
2. The PDF, when no source exists. Text extraction loses table structure and math, so
   treat extracted tables and equations as hints and check them against the page image.

Put each paper in `papers/` as a PDF, a `.tex` file, or a folder of LaTeX source, then run:

```bash
python3 <kit>/scripts/paper_text.py papers thesis-work/papers
```

It writes `thesis-work/papers/<id>/source.txt` (and `source.tex` for LaTeX) plus
`meta.json`, and it never overwrites an existing `source.txt` unless you pass `--force`.

## Look at the page when it matters

Extracted text is enough for prose. For a table, an equation, an algorithm or a figure
caption, look at the page:

```bash
python3 <kit>/scripts/render_pages.py papers/<file>.pdf --pages 4 --dpi 200
python3 <kit>/scripts/render_pages.py papers/<file>.pdf --pages 4 --crop 0,0.55,1,0.45
```

Then open the printed PNG path with the Read tool. The Read tool also opens a PDF
directly (`pages: "3-5"`, at most 20 pages per call), which is the quickest way to read a
whole short paper with its tables and figures intact.

If Anthropic's `pdf` skill is available, use it for table extraction (pdfplumber) and for
OCR of scanned pages. If MinerU, Marker or Docling is installed, it gives better math and
tables than pdftotext; still compare its output with the page image before trusting a
table.

## Figures

Prefer the original figure files from the LaTeX source. From a PDF, extract embedded
images with `pdfimages -png -f <page> -l <page> paper.pdf out/fig`, or render the figure's
region at 300 dpi with `render_pages.py --crop`. Vector figures do not survive
`pdfimages`; render them instead.

## Bibliography

Take `.bib` entries from the paper's source when you have it. From a PDF, build entries
from its reference list, then check them: `academic-refchecker` (MIT, `pip install
academic-refchecker`, run with `--no-llm`) verifies entries against Semantic Scholar,
OpenAlex and others; a DOI lookup on crossref.org works for single entries. Never invent
a field you could not verify; leave it out and list the entry in `escalations.md`.

## Check a re-typeset table or equation

1. Render the source page crop and the compiled thesis page crop, and view both.
2. Compare cell by cell (or symbol by symbol), including bold marks and footnotes.
3. Run `check_numbers.py` on the chapter against the paper.
