#!/usr/bin/env python3
"""LaTeX to PDF converter using fpdf2."""

import os
import sys
import re


def handle(args, cwd, stdin_data=""):
    """Convert .tex to .pdf using fpdf2. Args = .tex file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: latex_pdf <filepath.tex>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    # Read .tex file
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            tex_content = f.read()
    except Exception as e:
        return {"ok": False, "error": "Cannot read file: {}".format(str(e))}

    # Try fpdf2
    try:
        from fpdf import FPDF
    except ImportError:
        return {"ok": False, "error": "fpdf2 not installed. Install: pip install fpdf2"}

    # Parse LaTeX content into sections
    sections = _parse_latex(tex_content)

    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Title page
        title = _extract_title(tex_content) or os.path.basename(fpath)
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 15, title, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(10)

        # Process sections
        pdf.set_font("Helvetica", "", 11)
        for section in sections:
            sec_type = section.get("type", "text")
            content = section.get("content", "").strip()

            if not content:
                continue

            if sec_type == "section":
                pdf.ln(5)
                pdf.set_font("Helvetica", "B", 14)
                pdf.multi_cell(0, 8, _strip_latex(content))
                pdf.set_font("Helvetica", "", 11)
            elif sec_type == "subsection":
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 12)
                pdf.multi_cell(0, 7, _strip_latex(content))
                pdf.set_font("Helvetica", "", 11)
            elif sec_type == "itemize" or sec_type == "enumerate":
                for item in content.split("\n"):
                    item = item.strip().lstrip("- ").lstrip("\\item ").strip()
                    if item:
                        pdf.multi_cell(0, 6, "  - " + _strip_latex(item))
            elif sec_type == "code":
                pdf.set_font("Courier", "", 9)
                for code_line in content.split("\n"):
                    pdf.cell(0, 5, code_line[:100], new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 11)
            else:
                clean = _strip_latex(content)
                if clean:
                    pdf.multi_cell(0, 6, clean)

        # Output PDF
        out_path = os.path.splitext(fpath)[0] + ".pdf"
        pdf.output(out_path)

        return {
            "ok": True,
            "msg": "PDF created: {}".format(out_path),
            "output": out_path,
            "pages": pdf.page_no(),
            "sections": len(sections),
        }
    except Exception as e:
        return {"ok": False, "error": "PDF generation failed: {}".format(str(e))}


def _extract_title(tex):
    """Extract title from LaTeX document."""
    m = re.search(r'\\title\{([^}]+)\}', tex)
    if m:
        return _strip_latex(m.group(1))
    return ""


def _parse_latex(tex):
    """Parse LaTeX into sections."""
    sections = []
    lines = tex.split("\n")
    current_type = "text"
    current_content = []

    # Skip preamble (before \begin{document})
    doc_start = -1
    for i, line in enumerate(lines):
        if r"\begin{document}" in line:
            doc_start = i + 1
            break

    start = doc_start if doc_start >= 0 else 0

    for i in range(start, len(lines)):
        line = lines[i]
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("%"):
            continue

        # Section headers
        if stripped.startswith(r"\section"):
            if current_content:
                sections.append({"type": current_type, "content": "\n".join(current_content)})
            current_type = "section"
            m = re.search(r'\\section\*?\{([^}]+)\}', stripped)
            current_content = [m.group(1) if m else stripped]
            continue

        if stripped.startswith(r"\subsection"):
            if current_content:
                sections.append({"type": current_type, "content": "\n".join(current_content)})
            current_type = "subsection"
            m = re.search(r'\\subsection\*?\{([^}]+)\}', stripped)
            current_content = [m.group(1) if m else stripped]
            continue

        # Itemize
        if r"\begin{itemize}" in stripped or r"\begin{enumerate}" in stripped:
            if current_content:
                sections.append({"type": current_type, "content": "\n".join(current_content)})
            current_type = "itemize"
            current_content = []
            continue
        if r"\end{itemize}" in stripped or r"\end{enumerate}" in stripped:
            sections.append({"type": current_type, "content": "\n".join(current_content)})
            current_type = "text"
            current_content = []
            continue

        # Code blocks (verbatim)
        if r"\begin{verbatim}" in stripped:
            if current_content:
                sections.append({"type": current_type, "content": "\n".join(current_content)})
            current_type = "code"
            current_content = []
            continue
        if r"\end{verbatim}" in stripped:
            sections.append({"type": current_type, "content": "\n".join(current_content)})
            current_type = "text"
            current_content = []
            continue

        # Skip end document
        if r"\end{document}" in stripped:
            break

        # Skip common LaTeX commands
        if stripped.startswith((r"\documentclass", r"\usepackage", r"\author", r"\date",
                                r"\maketitle", r"\tableofcontents")):
            continue

        current_content.append(line)

    if current_content:
        sections.append({"type": current_type, "content": "\n".join(current_content)})

    return sections


def _strip_latex(text):
    """Remove basic LaTeX commands from text."""
    # Remove common commands but keep their content
    text = re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textit\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\underline\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\emph\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\url\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\item\s*', '', text)
    text = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r'\s+', ' ', text).strip()
    return text


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out.get("error", str(out))))