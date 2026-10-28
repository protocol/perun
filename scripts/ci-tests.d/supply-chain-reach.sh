# supply_chain_check.sh osv reach tags (imported, dev-only, transitive); non-imported rows skip the gate unless SUPPLY_CHAIN_STRICT=1.
python3 scripts/test_supply_chain_reach.py
