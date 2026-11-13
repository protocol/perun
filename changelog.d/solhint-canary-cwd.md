### Fixed
- The review hub's solhint canary now runs from its throwaway directory. solhint 6.x aborts with a RangeError (exit 255, no output) on a file outside its working directory, so the canary never raised avoid-tx-origin and solhint was reported as not run. The fail-closed guard is unchanged.
- test-review-checks-real-hub.sh no longer prints "Broken pipe" when it shows a tool's raw output after a failure.
