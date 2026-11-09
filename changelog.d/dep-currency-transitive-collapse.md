### Changed
- `dependency_currency.py` TSV output collapses outdated transitive npm packages (lockfile names that no sibling `package.json` or lock root declares directly) into one outdated row per lockfile when there are more than 3, naming the first 3 and counting the major-behind ones. Direct rows, vulnerable rows, non-npm files and `--json` (every row) print unchanged.
