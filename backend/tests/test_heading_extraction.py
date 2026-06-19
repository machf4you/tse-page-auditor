"""
V1.1 — verify heading extraction is scoped to main content and ignores
nav / footer / sidebar / widget blocks.

Reproduces the bug found on a live SEO Services audit where these
noise headings leaked into the H2 list:
  - Sheridan France
  - Cheap Bed Sale
  - Floor-to-Ceiling Fitted Furniture
  - Menu
  - Company
  - Copyright (c) 2026
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit.extractor import extract


NOISY_HTML = """<!doctype html>
<html><head><title>SEO Services</title></head>
<body>
  <header class="site-header">
    <h2>Menu</h2>
    <nav class="navigation"><h2>Company</h2><a href="/about/">About</a></nav>
  </header>

  <main>
    <h1>SEO Services</h1>
    <h2>What our SEO services include</h2>
    <p>Detailed SEO services copy here.</p>
    <h2>FAQ about SEO services</h2>
    <p>Answers.</p>
  </main>

  <aside class="sidebar widget-area">
    <h2>Cheap Bed Sale</h2>
    <h2>Floor-to-Ceiling Fitted Furniture</h2>
    <h3>Sheridan France</h3>
  </aside>

  <section class="testimonials">
    <h2>What clients say</h2>
    <p>Glowing review.</p>
  </section>

  <footer class="page-footer">
    <h2>Copyright (c) 2026</h2>
    <h3>Footer links</h3>
  </footer>
</body></html>
"""


def test_headings_only_from_main_content():
    ex = extract(NOISY_HTML, "https://x.test/seo-services/", 200, 10, "http",
                 "https://x.test/seo-services/")
    # H1 in <main> survives.
    assert ex.h1 == ["SEO Services"]
    # H2s should ONLY come from <main> — not from header / nav / aside /
    # testimonials / footer.
    assert ex.h2 == [
        "What our SEO services include",
        "FAQ about SEO services",
    ]
    # H3 from sidebar must not leak in.
    assert "Sheridan France" not in ex.h3
    # Body text must not include footer copyright noise.
    assert "Copyright" not in ex.body_text
    assert "Cheap Bed Sale" not in ex.body_text
    assert "Menu" not in ex.body_text
    # But genuine content stays.
    assert "Detailed SEO services copy here." in ex.body_text


def test_headings_fall_back_to_body_when_no_main_tag():
    """When there's no <main>/<article>, we still strip layout blocks."""
    html = """<!doctype html><html><body>
      <nav><h2>Top menu</h2></nav>
      <h1>Spanish Residency Services</h1>
      <h2>What we do</h2>
      <footer><h2>Copyright</h2></footer>
    </body></html>"""
    ex = extract(html, "https://x.test/", 200, 1, "http", "https://x.test/")
    assert ex.h1 == ["Spanish Residency Services"]
    assert ex.h2 == ["What we do"]


def test_nested_header_inside_article_is_kept():
    """A <header> nested inside <article> is article-level content, not layout."""
    html = """<!doctype html><html><body>
      <header class="site-header"><h2>Top nav</h2></header>
      <article>
        <header><h1>Article title</h1></header>
        <h2>Body section</h2>
      </article>
    </body></html>"""
    ex = extract(html, "https://x.test/post/", 200, 1, "http", "https://x.test/post/")
    assert ex.h1 == ["Article title"]
    assert ex.h2 == ["Body section"]


def test_wordpress_elementor_widgets_are_not_stripped():
    """
    Real-world regression: page builders (Elementor / Divi / Beaver Builder /
    Gutenberg) wrap their content blocks in containers with class names like
    `elementor-widget`, `elementor-element`, `nav-menu` etc. The earlier V1.1
    layout filter matched any class containing the word `widget` / `nav` and
    silently stripped the whole page, leaving h1=[], h2=[], word_count=~9.
    The Civion residency page reproduced this exactly. The fixture below is
    a stripped-down version of the same DOM shape.
    """
    html = """<!doctype html>
    <html><head><title>Spanish Residency Services</title></head>
    <body class="wp-singular">
      <nav class="main-nav"><a href="/">Home</a></nav>
      <div class="elementor elementor-186">
        <div class="elementor-element elementor-element-516e">
          <div class="elementor-element elementor-widget">
            <h1>Residency Services for Expats in Spain</h1>
          </div>
          <div class="elementor-element elementor-widget">
            <h2>TIE Card Application</h2>
            <p>Detailed copy about TIE cards goes here.</p>
          </div>
          <div class="elementor-element elementor-widget">
            <h2>NIE Number Application</h2>
            <p>Detailed copy about NIE numbers goes here.</p>
          </div>
        </div>
      </div>
      <footer class="page-footer"><h2>Copyright 2026</h2></footer>
    </body></html>"""
    ex = extract(html, "https://x.test/", 200, 1, "http", "https://x.test/")
    assert ex.h1 == ["Residency Services for Expats in Spain"]
    assert ex.h2 == ["TIE Card Application", "NIE Number Application"]
    assert ex.word_count > 10
    # Footer copy is still stripped (semantic <footer>).
    assert "Copyright" not in ex.body_text
