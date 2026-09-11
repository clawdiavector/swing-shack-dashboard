# Agent notes

## `data/` is seed-only

The repo `data/` tree (and the image copy under `BUNDLED_DATA_DIR`) is **seed data**: committed by humans only, read-only at runtime. Runtime truth lives in `$DATA_DIR` (Railway volume). No job, script, or workflow may write to `REPO_ROOT/data` or `git add` files under `data/`.
