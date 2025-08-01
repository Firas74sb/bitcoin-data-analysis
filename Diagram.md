# Diagramme de Flux de Bitcoin
 ```mermaid
 graph TD
    A[Fichiers Parquets] -->B{Polars}
    B --> C[Networkx]
    C --> D[python-louvain]
    D --> E[Pyvis]
    E --> F[HTML/JS/CSS]
```
