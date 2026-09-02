# Understanding PaperWeave graphs

PaperWeave builds corpus-local graphs after analysis.

## Paper graph

Each node is one scholarly work. Edges have different meanings:

| Edge | Meaning |
| --- | --- |
| `citation`, `verified` | A reference matched another corpus paper by DOI or arXiv ID |
| `citation`, `candidate` | A title similarity suggests a citation; review is required |
| `related`, `computed` | Papers share datasets, taxonomy, method language, or references |

A related edge is not a citation and does not prove scientific similarity. Its
score and contributing signals are written to `records/citation_graph.json`.

## Knowledge graph

The heterogeneous graph adds dataset and taxonomy nodes:

```text
Paper ──evaluated_on──> Dataset
Paper ──classified_as─> Taxonomy label
Paper ──citation──────> Paper
Paper ──related─────── Paper
```

## Files

- `synthesis/citation_graph.md`: readable summary;
- `records/citation_graph.json`: paper nodes, edges, status, and scores;
- `records/paper_graph.graphml`: paper-only graph for Gephi/Cytoscape;
- `records/knowledge_graph.json`: heterogeneous graph;
- `records/knowledge_graph.graphml`: heterogeneous GraphML export.

Only papers already in the corpus are considered. PaperWeave does not currently
expand a seed paper through the global citation network as Connected Papers or
Litmaps do.
