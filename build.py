#!/usr/bin/env python3
"""Generate the portfolio site from content.json into dist/."""

import html
import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?){2}\d{4}(?!\d)|(?<!\d)[6-9]\d{9}(?!\d)"
)


def e(value) -> str:
    return html.escape(str(value), quote=True)


def site_root(site: dict) -> str:
    url = str(site.get("url", "")).strip().rstrip("/")
    if not url.startswith("https://"):
        raise SystemExit("site.url must be an absolute https URL")
    return url + "/"


def abs_url(root: str, path: str) -> str:
    return root + path.lstrip("/")


def nowrap(escaped: str) -> str:
    escaped = re.sub(r"\b(v\d+-to-v\d+)\b", r'<span class="nw">\1</span>', escaped)
    escaped = re.sub(r"\b(\d+-[A-Za-z]+)\b", r'<span class="nw">\1</span>', escaped)
    return escaped


def time_tag(label: str) -> str:
    shown = e(label)
    parts = label.split()
    if len(parts) == 2 and parts[0] in MONTHS and parts[1].isdigit():
        return f'<time datetime="{parts[1]}-{MONTHS[parts[0]]}">{shown}</time>'
    return f"<time>{shown}</time>"


def value_class(value: str) -> str:
    classes = "stat-value grad"
    if len(value) > 8:
        classes += " is-long"
    return classes


def render_stat(item: dict) -> str:
    detail = item.get("detail") or ""
    detail_html = f'<p class="stat-detail">{e(detail)}</p>' if detail else ""
    wide = " stat-wide" if "pair" in item else ""
    if "pair" in item:
        cells = []
        for part in item["pair"]:
            cells.append(
                "<li>"
                f'<p class="{value_class(part["value"])}">{e(part["value"])}</p>'
                f'<p class="stat-label">{e(part["label"])}</p>'
                "</li>"
            )
        body = f'<ul class="stat-pair">{"".join(cells)}</ul>{detail_html}'
    else:
        body = (
            f'<p class="{value_class(item["value"])}">{e(item["value"])}</p>'
            f'<p class="stat-label">{e(item["label"])}</p>'
            f"{detail_html}"
        )
    return f'<article class="stat{wide}">{body}</article>'


def link_label(url: str) -> str:
    return url.split("//", 1)[-1].replace("www.", "")


def load_font(path: Path, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), size)
    if weight is not None and hasattr(font, "set_variation_by_axes"):
        try:
            font.set_variation_by_axes([weight])
        except OSError:
            pass
    return font


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def gradient_fill(size, stops):
    width, height = size
    img = Image.new("RGB", size)
    pixels = img.load()
    span = max(width + height - 2, 1)
    for y in range(height):
        for x in range(width):
            t = (x + y) / span
            left = stops[0][1]
            right = stops[-1][1]
            for i in range(1, len(stops)):
                if t <= stops[i][0]:
                    prev_t, left = stops[i - 1]
                    next_t, right = stops[i]
                    local = 0 if next_t == prev_t else (t - prev_t) / (next_t - prev_t)
                    pixels[x, y] = lerp(left, right, local)
                    break
            else:
                pixels[x, y] = stops[-1][1]
    return img


def text_mask(lines, font, fill_width, line_gap):
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    heights = []
    for line in lines:
        box = probe.textbbox((0, 0), line, font=font)
        heights.append(box[3] - box[1])
    line_h = max(heights) if heights else font.size
    height = line_h * len(lines) + line_gap * (len(lines) - 1)
    mask = Image.new("L", (fill_width, max(height, 1)), 0)
    draw = ImageDraw.Draw(mask)
    y = 0
    for line, h in zip(lines, heights):
        draw.text((0, y - probe.textbbox((0, 0), line, font=font)[1]), line, font=font, fill=255)
        y += line_h + line_gap
    return mask


def paste_gradient_text(base, xy, lines, font, max_width):
    mask = text_mask(lines, font, max_width, 6)
    colors = gradient_fill(
        mask.size,
        [
            (0.0, (239, 234, 255)),
            (0.26, (196, 182, 255)),
            (0.58, (122, 162, 255)),
            (1.0, (62, 224, 197)),
        ],
    )
    layer = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    layer.paste(colors, mask=mask)
    base.alpha_composite(layer, xy)


def render_og(content, dest: Path, page_url: str):
    width, height = 1200, 630
    canvas = Image.new("RGBA", (width, height), (7, 8, 15, 255))
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-120, -160, 560, 460), fill=(124, 108, 255, 110))
    glow_draw.ellipse((680, -180, 1320, 420), fill=(62, 224, 197, 80))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(70)))
    grid = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    for x in range(0, width, 60):
        grid_draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 18))
    for y in range(0, height, 60):
        grid_draw.line([(0, y), (width, y)], fill=(255, 255, 255, 18))
    canvas.alpha_composite(grid)

    display = load_font(ROOT / "fonts" / "space-grotesk.ttf", 68, 600)
    body = load_font(ROOT / "fonts" / "inter-400.ttf", 26)
    small = load_font(ROOT / "fonts" / "inter-600.ttf", 22)
    draw = ImageDraw.Draw(canvas)
    headline = content["headline"]
    if "AI " in headline:
        head, tail = headline.split("AI ", 1)
        lines = [head + "AI", tail]
    else:
        lines = [headline]
    draw.text((80, 128), f"{content['name']}  ·  {content['location']}", font=small, fill=(168, 176, 192))
    words = content["valueStatement"].split()
    wrapped, current = [], ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=body) <= 820:
            current = trial
        else:
            wrapped.append(current)
            current = word
    if current:
        wrapped.append(current)
    y = 210 + 78 * len(lines) + 28
    for line in wrapped[:3]:
        draw.text((80, y), line, font=body, fill=(168, 176, 192))
        y += 38
    host = page_url.replace("https://", "").rstrip("/")
    draw.text((80, 560), host, font=small, fill=(168, 176, 192))
    # Draw after ImageDraw calls. A Draw object keeps a stale buffer and would erase this.
    paste_gradient_text(canvas, (80, 200), lines, display, 980)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(dest, "PNG", optimize=True)


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def render_icon(size, dest: Path, rounded: bool):
    color = gradient_fill(
        (size, size),
        [(0.0, (201, 184, 255)), (0.5, (147, 212, 255)), (1.0, (111, 240, 212))],
    ).convert("RGBA")
    if rounded:
        color.putalpha(rounded_mask(size, int(size * 0.22)))
    font = load_font(ROOT / "fonts" / "space-grotesk.ttf", int(size * 0.38), 600)
    draw = ImageDraw.Draw(color)
    text = "AK"
    box = draw.textbbox((0, 0), text, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), text, font=font, fill=(16, 18, 26, 255))
    dest.parent.mkdir(parents=True, exist_ok=True)
    color.save(dest, "PNG")


def write_favicon_svg(dest: Path):
    dest.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#c9b8ff"/>
      <stop offset="0.5" stop-color="#93d4ff"/>
      <stop offset="1" stop-color="#6ff0d4"/>
    </linearGradient>
  </defs>
  <rect width="32" height="32" rx="8" fill="url(#g)"/>
  <text x="16" y="21" text-anchor="middle" font-family="Inter, system-ui, sans-serif" font-size="13" font-weight="700" fill="#10121a">AK</text>
</svg>
""",
        encoding="utf-8",
    )


REVEAL_JS = """<script>
(function () {
  document.documentElement.classList.add("js");
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!("IntersectionObserver" in window)) return;
  var nodes = document.querySelectorAll(".reveal");
  var vh = window.innerHeight || 800;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("in");
      io.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
  nodes.forEach(function (node) {
    if (node.getBoundingClientRect().top < vh * 0.92) node.classList.add("in", "seen");
    else io.observe(node);
  });
})();
</script>
"""


def current_role(content):
    for job in content["experience"]:
        if str(job["end"]).lower() == "present":
            return job
    return content["experience"][0]


def audit(content, page):
    bullets = "\n".join(b for job in content["experience"] for b in job["bullets"])
    lowered = bullets.lower()
    for item in content["highlights"]["items"]:
        source = item["source"]
        if source.lower() not in lowered:
            raise SystemExit(f"Highlight source is not in the experience bullets: {source}")
        for number in re.findall(r"\d[\d,]*", json.dumps(item)):
            if number not in bullets:
                raise SystemExit(f"Highlight number {number} is not in the experience bullets")

    if "jenkins" in lowered:
        raise SystemExit("Jenkins appears in the CSG experience bullets")
    clone = json.loads(json.dumps(content))
    for group in clone["skills"]:
        group["items"] = [item for item in group["items"] if "jenkins" not in item.lower()]
    for project in clone["projects"]:
        if project.get("name") == "DevOps Automation Project":
            project["description"] = re.sub(r"jenkins", "", project.get("description", ""), flags=re.I)
    if "jenkins" in json.dumps(clone).lower():
        raise SystemExit("Jenkins appears outside skill tags and the DevOps Automation Project")
    page_rest = re.sub(r'<section id="(?:skills|projects)".*?</section>', "", page, flags=re.S | re.I)
    if "jenkins" in page_rest.lower():
        raise SystemExit("Jenkins appears outside skills and projects in the generated page")

    blob = json.dumps(content) + "\n" + page
    if PHONE_RE.search(blob):
        raise SystemExit("A phone-like number is present in the site content or HTML")
    for banned in ("telephone", "phone"):
        if re.search(rf"\b{banned}\b", blob, re.I):
            raise SystemExit(f"Found {banned!r} in site content or HTML")


def build():
    content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    root = site_root(content["site"])
    pdf_path = (ROOT / content["resume"]["path"]).resolve()
    if not pdf_path.is_relative_to(ROOT.resolve()) or not pdf_path.is_file():
        raise SystemExit(f"Resume PDF not found at {content['resume']['path']}")

    role = current_role(content)
    locality, _, country = content["location"].partition(",")
    country = country.strip() or locality.strip()
    country_code = "IN" if country.lower() == "india" else country
    person = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": content["name"],
        "jobTitle": role["role"],
        "url": root,
        "email": "mailto:" + content["contact"]["email"],
        "address": {
            "@type": "PostalAddress",
            "addressLocality": locality.strip(),
            "addressCountry": country_code,
        },
        "worksFor": {"@type": "Organization", "name": role["company"]},
        "sameAs": [content["contact"]["linkedin"], content["contact"]["github"]],
    }
    if "telephone" in person or "phone" in json.dumps(person).lower():
        raise SystemExit("JSON-LD must not include a phone number")
    ld_json = json.dumps(person, ensure_ascii=False).replace("<", "\\u003c")

    jobs = []
    for job in content["experience"]:
        items = "".join(f"<li>{nowrap(e(bullet))}</li>" for bullet in job["bullets"])
        bullet_html = f"<ul>{items}</ul>" if items else ""
        jobs.append(
            f"""<article class="job">
        <header class="row">
          <h3>{e(job["role"])} <span class="muted">· {e(job["company"])}</span></h3>
          <p class="muted date">{time_tag(job["start"])} – {time_tag(job["end"])}</p>
        </header>
        {bullet_html}
      </article>"""
        )

    skills = []
    for group in content["skills"]:
        tags = "".join(f"<li>{e(item)}</li>" for item in group["items"])
        skills.append(
            f'<div class="skill-row"><h3>{e(group["group"])}</h3><ul class="tags">{tags}</ul></div>'
        )

    projects = []
    for project in content["projects"]:
        badge = f' <span class="badge">{e(project["status"])}</span>' if project.get("status") else ""
        projects.append(
            f'<article class="project"><h3>{e(project["name"])}{badge}</h3><p>{e(project["description"])}</p></article>'
        )

    highlights = "".join(render_stat(item) for item in content["highlights"]["items"])
    contact = content["contact"]
    resume = content["resume"]
    og_path = content["site"]["ogImage"]
    title = content["site"]["title"]
    description = content["site"]["description"]
    image_alt = f"{content['name']}, {content['headline']}"

    page = f"""<!doctype html>
<html lang="{e(content["site"]["lang"])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta name="author" content="{e(content["name"])}">
<meta name="theme-color" content="#07080f">
<meta name="color-scheme" content="dark">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{e(root)}">
<meta property="og:type" content="profile">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(root)}">
<meta property="og:image" content="{e(abs_url(root, og_path))}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(image_alt)}">
<meta property="og:locale" content="en_IN">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(description)}">
<meta name="twitter:image" content="{e(abs_url(root, og_path))}">
<meta name="twitter:image:alt" content="{e(image_alt)}">
<script type="application/ld+json">{ld_json}</script>
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" href="favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="preload" href="fonts/space-grotesk.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="fonts/inter-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap bar">
    <a class="brand" href="#top">{e(content["name"])}</a>
    <nav aria-label="Primary">
      <ul>
        <li><a href="#experience">Experience</a></li>
        <li><a href="#skills">Skills</a></li>
        <li><a href="#projects">Projects</a></li>
        <li><a href="#contact">Contact</a></li>
      </ul>
    </nav>
  </div>
</header>
<main id="main">
  <section id="top" class="hero" aria-labelledby="page-title">
    <div class="hero-bg" aria-hidden="true">
      <div class="orb orb-a"></div>
      <div class="orb orb-b"></div>
      <div class="gridlines"></div>
    </div>
    <div class="wrap">
      <p class="eyebrow">{e(content["name"])} <span class="muted">· {e(content["location"])}</span></p>
      <h1 id="page-title" class="grad">{e(content["headline"])}</h1>
      <p class="lede">{e(content["valueStatement"])}</p>
      <p class="actions">
        <a class="btn primary" href="{e(resume["path"])}" download="{e(Path(resume["path"]).name)}">{e(resume["heroLabel"])}</a>
        <a class="btn" href="#contact">Contact</a>
      </p>
    </div>
  </section>

  <section id="highlights" class="wrap highlights reveal" aria-labelledby="h-highlights">
    <h2 id="h-highlights">{e(content["highlights"]["heading"])}</h2>
    <div class="bento">{highlights}</div>
  </section>

  <section id="about" class="wrap block reveal" aria-labelledby="h-about">
    <h2 id="h-about">About</h2>
    <p class="body">{e(content["summary"])}</p>
  </section>

  <section id="experience" class="wrap block reveal" aria-labelledby="h-exp">
    <h2 id="h-exp">Experience</h2>
    <div>
      {"".join(jobs)}
      <p class="muted award">{e(content["award"])}</p>
    </div>
  </section>

  <section id="skills" class="wrap block reveal" aria-labelledby="h-skills">
    <h2 id="h-skills">Skills</h2>
    <div>{"".join(skills)}</div>
  </section>

  <section id="projects" class="wrap block reveal" aria-labelledby="h-proj">
    <h2 id="h-proj">Projects</h2>
    <div>{"".join(projects)}</div>
  </section>

  <section id="resume" class="wrap block reveal" aria-labelledby="h-resume">
    <h2 id="h-resume">Resume</h2>
    <div>
      <p class="body">{e(resume["blurb"])}</p>
      <p class="actions"><a class="btn primary" href="{e(resume["path"])}" download="{e(Path(resume["path"]).name)}">{e(resume["label"])}</a></p>
    </div>
  </section>

  <section id="contact" class="wrap block reveal" aria-labelledby="h-contact">
    <h2 id="h-contact">Contact</h2>
    <ul class="contact">
      <li><span class="muted">Email</span><a href="mailto:{e(contact["email"])}">{e(contact["email"])}</a></li>
      <li><span class="muted">LinkedIn</span><a href="{e(contact["linkedin"])}" rel="me noopener">{e(link_label(contact["linkedin"]))}</a></li>
      <li><span class="muted">GitHub</span><a href="{e(contact["github"])}" rel="me noopener">{e(link_label(contact["github"]))}</a></li>
    </ul>
  </section>
</main>
<footer class="wrap foot">© {e(content["site"]["year"])} {e(content["name"])}</footer>
{REVEAL_JS}
</body>
</html>
"""

    audit(content, page)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    (DIST / "index.html").write_text(page, encoding="utf-8")
    shutil.copy(ROOT / "styles.css", DIST / "styles.css")
    font_dir = DIST / "fonts"
    font_dir.mkdir()
    for name in ("inter-400.woff2", "inter-600.woff2", "space-grotesk.woff2"):
        shutil.copy(ROOT / "fonts" / name, font_dir / name)
    dest_pdf = DIST / content["resume"]["path"]
    dest_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(pdf_path, dest_pdf)
    render_og(content, DIST / og_path, root)
    render_icon(32, DIST / "favicon-32.png", rounded=True)
    render_icon(180, DIST / "apple-touch-icon.png", rounded=False)
    write_favicon_svg(DIST / "favicon.svg")
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {abs_url(root, 'sitemap.xml')}\n",
        encoding="utf-8",
    )
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{root}</loc></url>\n"
        "</urlset>\n",
        encoding="utf-8",
    )
    print(f"wrote {DIST}")


if __name__ == "__main__":
    build()
