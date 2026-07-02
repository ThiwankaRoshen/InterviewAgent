

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch
import markdown2
 

def markdown_to_pdf(markdown_text: str, output_path: str):
    """
    Convert a markdown report into a readable PDF.
    """

    styles = getSampleStyleSheet()

    title_style = styles["Heading1"]
    title_style.alignment = TA_CENTER

    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    normal = styles["BodyText"]

    doc = SimpleDocTemplate(output_path)

    story = []

    lines = markdown_text.splitlines()

    for line in lines:

        line = line.strip()

        if not line:
            story.append(Spacer(1, 0.15 * inch))
            continue

        if line.startswith("# "):
            story.append(Paragraph(line[2:], title_style))

        elif line.startswith("## "):
            story.append(Paragraph(line[3:], h1))

        elif line.startswith("### "):
            story.append(Paragraph(line[4:], h2))

        elif line.startswith("- "):
            story.append(Paragraph(f"• {line[2:]}", normal))

        else:
            story.append(Paragraph(line, normal))

    doc.build(story)