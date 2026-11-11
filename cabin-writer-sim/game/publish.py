"""Publication: turns a finished manuscript into real deliverables —

  * an EPUB (valid EPUB 2/3 hybrid, hand-assembled zip)
  * a PDF  (hand-written, dependency-free, Helvetica)
  * both carry an ownership certificate naming the user as owner
  * everything packaged in a neatly organised .zip (or flat, on request)

No third-party libraries are used so an AI agent can run this anywhere.
"""

import hashlib
import io
import json
import os
import textwrap
import time
import zipfile
from xml.sax.saxutils import escape as xesc

# ------------------------------------------------------------- certificate ---

def make_certificate(ms, owner):
    """Ownership certificate data, embedded in both file types."""
    canonical = canonical_text(ms)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    isbn = "978-0-%06d-%d" % (int(digest[:8], 16) % 900000 + 100000,
                              int(digest[8:10], 16) % 10)
    issued = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return {
        "title": ms["title"],
        "author": ms["author"],
        "owner": owner,
        "isbn": isbn,
        "issued": issued,
        "words": ms["words"],
        "sittings": ms["sessions"],
        "craft_score": ms["quality"],
        "manuscript_sha256": digest,
        "declaration": (
            f"This certifies that the literary work \"{ms['title']}\", "
            f"written by {ms['author']} within the Cabin Writer simulation, "
            f"is transferred in full — all rights, title, and interest — to "
            f"{owner}, its commissioner and sole owner. The work is original, "
            f"generated for {owner} alone, and certified by the SHA-256 "
            f"fingerprint of its complete manuscript recorded above."
        ),
        "signature": hashlib.sha256(
            f"{digest}|{owner}|{isbn}".encode()).hexdigest()[:32],
    }


def certificate_text(cert):
    line = "=" * 62
    return (
        f"{line}\n"
        f"  CERTIFICATE OF AUTHORSHIP AND OWNERSHIP\n"
        f"{line}\n\n"
        f"  Title        : {cert['title']}\n"
        f"  Written by   : {cert['author']}\n"
        f"  Owned by     : {cert['owner']}\n"
        f"  ISBN         : {cert['isbn']}\n"
        f"  Issued       : {cert['issued']}\n"
        f"  Length       : {cert['words']} words over {cert['sittings']} sittings\n"
        f"  Craft score  : {cert['craft_score']:.2f} / 1.00\n"
        f"  SHA-256      : {cert['manuscript_sha256']}\n"
        f"  Signature    : {cert['signature']}\n\n"
        f"{textwrap.fill(cert['declaration'], 62)}\n\n"
        f"{line}\n"
    )


def canonical_text(ms):
    parts = [ms["title"], ms["author"], ms["theme"]]
    parts += ms["preface"]
    for ch in ms["chapters"]:
        parts.append(f"Chapter {ch['number']}: {ch['title']}")
        parts += ch["paragraphs"]
    parts += ms["afterword"]
    return "\n\n".join(parts)


# ------------------------------------------------------------------- PDF ---
class _PDF:
    """A tiny, correct-enough PDF writer (single Helvetica font, A4-ish)."""

    def __init__(self):
        self.pages = []  # list of list of (size, text)

    def add_page(self, lines):
        self.pages.append(lines)

    @staticmethod
    def _esc(s):
        return (s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)"))

    def render(self):
        objects = []  # (id, body bytes); ids assigned in order
        n_pages = len(self.pages)
        # 1 catalog, 2 pages-tree, 3 font, then page/content pairs
        page_ids = [4 + 2 * i for i in range(n_pages)]
        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
        objects.append((2, f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>"
                        .encode()))
        objects.append((3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

        for i, lines in enumerate(self.pages):
            pid = page_ids[i]
            cid = pid + 1
            stream = ["BT"]
            y = 780
            stream.append(f"72 {y} Td")
            prev_size = None
            for size, text in lines:
                if size != prev_size:
                    stream.append(f"/F1 {size} Tf")
                    prev_size = size
                leading = int(size * 1.45)
                stream.append(f"0 -{leading} Td ({self._esc(text)}) Tj")
            stream.append("ET")
            data = "\n".join(stream).encode("latin-1", "replace")
            objects.append((pid, (f"<< /Type /Page /Parent 2 0 R /MediaBox "
                                  f"[0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                                  f"/Contents {cid} 0 R >>").encode()))
            objects.append((cid, b"<< /Length " + str(len(data)).encode() +
                            b" >>\nstream\n" + data + b"\nendstream"))

        out = io.BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for oid, body in objects:
            offsets[oid] = out.tell()
            out.write(f"{oid} 0 obj\n".encode())
            out.write(body)
            out.write(b"\nendobj\n")
        xref_pos = out.tell()
        count = max(offsets) + 1
        out.write(f"xref\n0 {count}\n".encode())
        out.write(b"0000000000 65535 f \n")
        for oid in range(1, count):
            out.write(f"{offsets.get(oid, 0):010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {count} /Root 1 0 R >>\n"
                  f"startxref\n{xref_pos}\n%%EOF".encode())
        return out.getvalue()


def _wrap(text, size):
    width = max(30, int(468 / (size * 0.5)))
    return textwrap.wrap(text, width) or [""]


def build_pdf(ms, cert):
    pdf = _PDF()
    # certificate first — the book belongs to the user before it begins
    cert_lines = [(16, "CERTIFICATE OF AUTHORSHIP"), (16, "AND OWNERSHIP"), (8, "")]
    for size, text in [(11, f"Title: {cert['title']}"),
                       (11, f"Written by: {cert['author']}"),
                       (11, f"Owned by: {cert['owner']}"),
                       (11, f"ISBN: {cert['isbn']}"),
                       (11, f"Issued: {cert['issued']}"),
                       (11, f"Words: {cert['words']}  Sittings: {cert['sittings']}"),
                       (11, f"Craft score: {cert['craft_score']:.2f} / 1.00"),
                       (9,  f"SHA-256: {cert['manuscript_sha256']}"),
                       (9,  f"Signature: {cert['signature']}"), (8, "")]:
        cert_lines.append((size, text))
    for wline in textwrap.wrap(cert["declaration"], 80):
        cert_lines.append((10, wline))
    pdf.add_page(cert_lines)

    # title page
    pdf.add_page([(8, ""), (8, ""), (24, ms["title"]), (8, ""),
                  (13, ms["theme"].capitalize()), (8, ""), (8, ""),
                  (12, f"by {ms['author']}"), (8, ""), (8, ""), (8, ""),
                  (10, "Written in the rain, for its owner.")])

    # epigraphs
    if ms["epigraphs"]:
        lines = [(8, "")]
        for ep in ms["epigraphs"]:
            for wl in _wrap(ep, 11):
                lines.append((11, wl))
            lines.append((8, ""))
        pdf.add_page(lines)

    def prose_pages(title, paragraphs):
        lines = [(15, title), (6, "")]
        for para in paragraphs:
            for wl in _wrap(para, 11):
                lines.append((11, wl))
            lines.append((4, ""))
        # paginate ~46 body-lines per page
        pages, cur, used = [], [], 0
        for size, text in lines:
            need = max(1, int(size * 1.45) // 14)
            if used + need > 46 and cur:
                pages.append(cur)
                cur, used = [], 0
            cur.append((size, text))
            used += need
        if cur:
            pages.append(cur)
        return pages

    for p in prose_pages("Preface", ms["preface"]):
        pdf.add_page(p)
    for ch in ms["chapters"]:
        for p in prose_pages(f"Chapter {ch['number']} — {ch['title']}",
                             ch["paragraphs"]):
            pdf.add_page(p)
    for p in prose_pages("Afterword", ms["afterword"]):
        pdf.add_page(p)
    return pdf.render()


# ------------------------------------------------------------------ EPUB ---
def _xhtml(title, body_html):
    return ("<?xml version='1.0' encoding='utf-8'?>\n"
            "<!DOCTYPE html>\n<html xmlns='http://www.w3.org/1999/xhtml'>\n"
            f"<head><title>{xesc(title)}</title>"
            "<link rel='stylesheet' href='../style.css'/></head>\n"
            f"<body>{body_html}</body>\n</html>")


def _paras(paragraphs):
    return "\n".join(f"<p>{xesc(p)}</p>" for p in paragraphs)


def build_epub(ms, cert):
    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, "w")

    # mimetype must be first and stored
    info = zipfile.ZipInfo("mimetype")
    info.compress_type = zipfile.ZIP_STORED
    zf.writestr(info, "application/epub+zip")

    zf.writestr("META-INF/container.xml",
                "<?xml version='1.0'?>\n"
                "<container version='1.0' "
                "xmlns='urn:oasis:names:tc:opendocument:xmlns:container'>"
                "<rootfiles><rootfile full-path='OEBPS/content.opf' "
                "media-type='application/oebps-package+xml'/>"
                "</rootfiles></container>")

    items, spine, navpoints = [], [], []
    playorder = 0

    def add_doc(fname, title, html):
        nonlocal playorder
        playorder += 1
        zf.writestr(f"OEBPS/text/{fname}", html)
        items.append(f"<item id='{fname[:-6]}' href='text/{fname}' "
                     f"media-type='application/xhtml+xml'/>")
        spine.append(f"<itemref idref='{fname[:-6]}'/>")
        navpoints.append(
            f"<navPoint id='nav{playorder}' playOrder='{playorder}'>"
            f"<navLabel><text>{xesc(title)}</text></navLabel>"
            f"<content src='text/{fname}'/></navPoint>")

    cert_html = (f"<h1>Certificate of Authorship and Ownership</h1>"
                 f"<p class='cert'><b>Title:</b> {xesc(cert['title'])}<br/>"
                 f"<b>Written by:</b> {xesc(cert['author'])}<br/>"
                 f"<b>Owned by:</b> {xesc(cert['owner'])}<br/>"
                 f"<b>ISBN:</b> {cert['isbn']}<br/>"
                 f"<b>Issued:</b> {cert['issued']}<br/>"
                 f"<b>Craft score:</b> {cert['craft_score']:.2f} / 1.00<br/>"
                 f"<b>SHA-256:</b> {cert['manuscript_sha256']}<br/>"
                 f"<b>Signature:</b> {cert['signature']}</p>"
                 f"<p>{xesc(cert['declaration'])}</p>")
    add_doc("certificate.xhtml", "Certificate of Ownership",
            _xhtml("Certificate", cert_html))

    tp = (f"<h1 class='title'>{xesc(ms['title'])}</h1>"
          f"<p class='theme'>{xesc(ms['theme'].capitalize())}</p>"
          f"<p class='byline'>by {xesc(ms['author'])}</p>")
    add_doc("title.xhtml", ms["title"], _xhtml(ms["title"], tp))

    if ms["epigraphs"]:
        ep = "\n".join(f"<p class='epigraph'>{xesc(e)}</p>"
                       for e in ms["epigraphs"])
        add_doc("epigraphs.xhtml", "Epigraphs", _xhtml("Epigraphs", ep))

    add_doc("preface.xhtml", "Preface",
            _xhtml("Preface", f"<h2>Preface</h2>{_paras(ms['preface'])}"))

    for ch in ms["chapters"]:
        body = (f"<h2>Chapter {ch['number']}</h2><h3>{xesc(ch['title'])}</h3>"
                + _paras(ch["paragraphs"]))
        add_doc(f"ch{ch['number']:02d}.xhtml",
                f"Chapter {ch['number']}: {ch['title']}",
                _xhtml(ch["title"], body))

    add_doc("afterword.xhtml", "Afterword",
            _xhtml("Afterword", f"<h2>Afterword</h2>{_paras(ms['afterword'])}"))

    uid = f"urn:cabinwriter:{cert['manuscript_sha256'][:16]}"
    zf.writestr("OEBPS/content.opf", f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns='http://www.idpf.org/2007/opf' unique-identifier='uid' version='2.0'>
  <metadata xmlns:dc='http://purl.org/dc/elements/1.1/'>
    <dc:title>{xesc(ms['title'])}</dc:title>
    <dc:creator>{xesc(ms['author'])}</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id='uid'>{uid}</dc:identifier>
    <dc:rights>Owned by {xesc(cert['owner'])}. ISBN {cert['isbn']}.</dc:rights>
    <dc:date>{cert['issued'][:10]}</dc:date>
    <meta name='cabinwriter:owner' content='{xesc(cert['owner'])}'/>
    <meta name='cabinwriter:sha256' content='{cert['manuscript_sha256']}'/>
  </metadata>
  <manifest>
    <item id='ncx' href='toc.ncx' media-type='application/x-dtbncx+xml'/>
    <item id='css' href='style.css' media-type='text/css'/>
    {''.join(items)}
  </manifest>
  <spine toc='ncx'>{''.join(spine)}</spine>
</package>""")

    zf.writestr("OEBPS/toc.ncx", f"""<?xml version='1.0' encoding='utf-8'?>
<ncx xmlns='http://www.daisy.org/z3986/2005/ncx/' version='2005-1'>
  <head><meta name='dtb:uid' content='{uid}'/></head>
  <docTitle><text>{xesc(ms['title'])}</text></docTitle>
  <navMap>{''.join(navpoints)}</navMap>
</ncx>""")

    zf.writestr("OEBPS/style.css", """
body { font-family: Georgia, 'Times New Roman', serif; margin: 2em;
       color: #23222a; background: #efe9dc; line-height: 1.55; }
h1.title { text-align: center; margin-top: 3em; font-size: 2em; }
h2 { margin-top: 2em; } h3 { font-style: italic; font-weight: normal; }
p { text-indent: 1.4em; margin: 0.5em 0; }
p.epigraph { text-indent: 0; font-style: italic; margin: 1.5em 2em; }
p.theme, p.byline { text-align: center; text-indent: 0; }
p.cert { text-indent: 0; font-size: 0.95em; }
""")
    zf.close()
    return buf.getvalue()


# ------------------------------------------------------------- packaging ---
def _slug(title):
    keep = [c if c.isalnum() else "-" for c in title.lower()]
    return "".join(keep).strip("-").replace("--", "-")[:48] or "book"


def package_book(ms, owner, out_dir, organized=True):
    """Write {slug}_{date}.zip containing the EPUB and PDF editions plus
    certificates and a plain-text manuscript. Returns the zip path."""
    os.makedirs(out_dir, exist_ok=True)
    cert = make_certificate(ms, owner)
    epub = build_epub(ms, cert)
    pdf = build_pdf(ms, cert)
    slug = _slug(ms["title"])
    date = time.strftime("%Y-%m-%d")
    zip_path = os.path.join(out_dir, f"{slug}_{date}.zip")

    manifest = {
        "title": ms["title"], "author": ms["author"], "owner": owner,
        "isbn": cert["isbn"], "issued": cert["issued"],
        "words": ms["words"], "craft_score": ms["quality"],
        "formats": ["epub", "pdf"], "organized": organized,
        "manuscript_sha256": cert["manuscript_sha256"],
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if organized:
            root = f"{slug}/"
            z.writestr(root + f"{slug}.epub", epub)
            z.writestr(root + f"{slug}.pdf", pdf)
            z.writestr(root + "certificates/CERTIFICATE.txt",
                       certificate_text(cert))
            z.writestr(root + "certificates/certificate.json",
                       json.dumps(cert, indent=2))
            z.writestr(root + "manuscript/00-preface.txt",
                       "\n\n".join(ms["preface"]))
            for ch in ms["chapters"]:
                body = (f"Chapter {ch['number']} — {ch['title']}\n\n"
                        + "\n\n".join(ch["paragraphs"]))
                z.writestr(root + f"manuscript/ch{ch['number']:02d}.txt", body)
            z.writestr(root + "manuscript/99-afterword.txt",
                       "\n\n".join(ms["afterword"]))
            z.writestr(root + "manifest.json", json.dumps(manifest, indent=2))
        else:
            # unorganized, as requested: everything dumped flat
            z.writestr(f"{slug}.epub", epub)
            z.writestr(f"{slug}.pdf", pdf)
            z.writestr(f"CERTIFICATE.txt", certificate_text(cert))
            z.writestr("certificate.json", json.dumps(cert, indent=2))
            for ch in ms["chapters"]:
                z.writestr(f"ch{ch['number']:02d}.txt",
                           "\n\n".join(ch["paragraphs"]))
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
    return zip_path
