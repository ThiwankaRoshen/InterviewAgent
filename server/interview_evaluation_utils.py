import markdown2
from weasyprint import HTML, CSS
from pathlib import Path

def markdown_to_pdf(markdown_text: str, output_path: str, css_path: str = None):
    """
    Convert a Markdown report to a beautifully styled PDF using WeasyPrint.
    """
    # Convert Markdown to HTML with all useful extras
    html_body = markdown2.markdown(
        markdown_text,
        extras=[
            "tables",
            "fenced-code-blocks",
            "break-on-newline",
            "strike",
            "task_list",
            "header-ids",
            "markdown-in-html",
        ]
    )

    # Professional default CSS – customise as you like
    default_css = """
    @page {
        size: A4;
        margin: 1.5cm 1.5cm 2cm 1.5cm;
        @top-center {
            content: "Interview Evaluation Report";
            font-size: 10pt;
            color: #666;
        }
        @bottom-center {
            content: "Page " counter(page) " of " counter(pages);
            font-size: 9pt;
            color: #999;
        }
    }

    body {
        font-family: 'Helvetica', 'Arial', sans-serif;
        font-size: 11pt;
        line-height: 1.5;
        color: #333;
    }

    h1 {
        font-size: 20pt;
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 6pt;
        margin-top: 20pt;
    }
    h2 {
        font-size: 16pt;
        color: #2c3e50;
        margin-top: 16pt;
    }
    h3 {
        font-size: 13pt;
        color: #34495e;
        margin-top: 12pt;
    }

    p {
        margin: 6pt 0;
    }

    ul, ol {
        margin: 6pt 0 6pt 20pt;
        padding-left: 0;
    }
    li {
        margin-bottom: 4pt;
    }

    table {
        border-collapse: collapse;
        width: 100%;
        margin: 12pt 0;
    }
    th, td {
        border: 1px solid #bdc3c7;
        padding: 6pt 8pt;
        text-align: left;
    }
    th {
        background-color: #ecf0f1;
        font-weight: bold;
    }

    code {
        font-family: 'Courier New', monospace;
        background-color: #f4f6f7;
        padding: 1pt 4pt;
        border-radius: 3px;
        font-size: 10pt;
    }
    pre {
        background-color: #f4f6f7;
        padding: 8pt;
        border-radius: 4px;
        overflow: auto;
        font-size: 10pt;
        border-left: 4px solid #3498db;
    }

    blockquote {
        margin: 10pt 0 10pt 20pt;
        padding: 6pt 12pt;
        background-color: #f9f9f9;
        border-left: 4px solid #7f8c8d;
        font-style: italic;
    }

    hr {
        border: 0;
        border-top: 1px solid #dce1e5;
        margin: 16pt 0;
    }

    .task-list-item {
        list-style-type: none;
    }
    .task-list-item input[type="checkbox"] {
        margin-right: 6px;
    }
    """

    # Optionally merge with a custom CSS file (if provided)
    if css_path and Path(css_path).exists():
        with open(css_path, 'r', encoding='utf-8') as f:
            custom_css = f.read()
        final_css = default_css + "\n" + custom_css
    else:
        final_css = default_css

    # Assemble full HTML and generate PDF
    html_string = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            {final_css}
        </style>
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """

    HTML(string=html_string).write_pdf(output_path, stylesheets=[CSS(string=final_css)])