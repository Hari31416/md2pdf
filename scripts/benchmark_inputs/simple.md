# Benchmark Test: Simple Document

This is a simple markdown document used to evaluate the baseline performance and compilation overhead of different Markdown-to-PDF engines.

## Document Features

The features tested in this simple document include:

- Basic headers (H1 and H2)
- Plain paragraphs with **bold** and *italic* formatting
- Standard unordered lists

### Additional Context

Rendering engines typically have a startup cost, such as loading fonts or launching headless browsers. A small document like this highlights the cold-start overhead vs. the actual typesetting computation.
