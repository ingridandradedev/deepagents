"""Chart generation and PDF report tools for the text-to-SQL agent."""

import csv
import io
import os
from datetime import datetime

from langchain_core.tools import tool

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _parse_csv_data(data: str) -> tuple[list[str], list[float]]:
    """Parse CSV string into labels and values."""
    reader = csv.reader(io.StringIO(data.strip()))
    labels, values = [], []
    for row in reader:
        if len(row) >= 2:
            labels.append(row[0].strip())
            try:
                values.append(float(row[1].strip()))
            except ValueError:
                continue
    return labels, values


@tool
def generate_chart(
    data: str,
    chart_type: str = "bar",
    title: str = "Chart",
    x_label: str = "",
    y_label: str = "",
    filename: str = "",
) -> str:
    """Generate a PNG chart from CSV data.

    Args:
        data: CSV string with two columns (label,value), one row per line.
              Example: "Brazil,190.10\\nGermany,156.48\\nFrance,120.00"
        chart_type: Type of chart - "bar", "line", or "pie".
        title: Chart title.
        x_label: X-axis label (ignored for pie charts).
        y_label: Y-axis label (ignored for pie charts).
        filename: Output filename (auto-generated if empty).

    Returns:
        Path to the saved PNG file.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _ensure_output_dir()

    labels, values = _parse_csv_data(data)
    if not labels:
        return "Error: No valid data to chart. Provide CSV with label,value rows."

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=140)
    elif chart_type == "line":
        ax.plot(labels, values, marker="o", linewidth=2)
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)
    else:  # bar
        ax.bar(labels, values)
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)

    ax.set_title(title)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chart_{ts}.png"
    if not filename.endswith(".png"):
        filename += ".png"

    filepath = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(filepath, dpi=150)
    plt.close(fig)

    return f"Chart saved: {filepath}"


@tool
def generate_pdf_report(
    title: str,
    sections: str,
    chart_paths: str = "",
    filename: str = "",
) -> str:
    """Generate a PDF report with text sections and embedded chart images.

    Args:
        title: Report title.
        sections: Report text content. Use "---" on its own line to separate
                  sections. Each section becomes a paragraph in the PDF.
        chart_paths: Comma-separated paths to PNG chart files to embed.
                     Example: "./output/chart1.png,./output/chart2.png"
        filename: Output filename (auto-generated if empty).

    Returns:
        Path to the saved PDF file.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    _ensure_output_dir()

    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{ts}.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"

    filepath = os.path.join(OUTPUT_DIR, filename)
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))

    # Date
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(f"Generated: {date_str}", styles["Normal"]))
    story.append(Spacer(1, 20))

    # Text sections
    for section in sections.split("---"):
        text = section.strip()
        if text:
            story.append(Paragraph(text, styles["Normal"]))
            story.append(Spacer(1, 12))

    # Embedded charts
    if chart_paths.strip():
        for path in chart_paths.split(","):
            path = path.strip()
            if os.path.exists(path):
                story.append(Spacer(1, 10))
                img = Image(path, width=6 * inch, height=4 * inch)
                story.append(img)
                story.append(Spacer(1, 12))

    doc.build(story)
    return f"PDF report saved: {filepath}"
