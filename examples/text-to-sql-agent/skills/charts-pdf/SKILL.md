---
name: charts-pdf
description: >-
  Generate charts (bar, line, pie) as PNG images and PDF reports with embedded
  text, tables, and charts. Use when the user asks to visualize data, create a
  chart, plot results, generate a graph, export a PDF report, or produce a
  visual analysis of query results.
---

# Charts & PDF Reports Skill

## When to Use

Activate this skill when the user mentions: chart, graph, plot, visualize,
PNG, PDF, report, dashboard, bar chart, pie chart, line chart, export.

## Available Tools

- `generate_chart` — Creates a PNG chart from query results
- `generate_pdf_report` — Creates a PDF report with text and embedded charts

## Workflow: Chart Only

1. Run the SQL query using `sql_db_query` to get the data
2. Call `generate_chart` with the query results, chart type, and labels
3. Tell the user where the chart was saved

## Workflow: PDF Report

1. Run one or more SQL queries to gather data
2. Generate charts with `generate_chart` for each dataset
3. Call `generate_pdf_report` with a title, text sections, and chart paths
4. Tell the user where the PDF was saved

## Chart Types

- `bar` — Compare categories (e.g., revenue by country, top artists)
- `line` — Show trends over time (e.g., monthly sales)
- `pie` — Show proportions (e.g., genre distribution)

## Examples

**User:** "Show me a bar chart of the top 5 artists by sales"
1. SQL: query top 5 artists with revenue
2. `generate_chart(data="Artist1,100\nArtist2,90...", chart_type="bar", title="Top 5 Artists by Sales", x_label="Artist", y_label="Revenue ($)")`

**User:** "Create a PDF report of sales by country with charts"
1. SQL: query sales by country
2. `generate_chart(...)` for bar chart
3. `generate_pdf_report(title="Sales Report", sections=[...], chart_paths=[...])`

## Guidelines

- Always use clear titles and axis labels
- Use LIMIT in queries to keep charts readable (5-10 items max)
- For PDF reports, include a brief text summary before each chart
- Save all outputs to the `./output/` directory
