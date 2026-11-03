#!/usr/bin/env python3
"""Self-test: numeric semver pre-releases ("5.0.0-2") must not count as stable for npm/cargo/composer."""
import snapshot as S

def test():
    vs = ["4.9.1", "5.0.0-2", "5.0.0-rc.1", "5.0.0-beta.2"]
    for eco in ("npm", "cargo", "composer"):
        assert S.stable(vs, eco) == ["4.9.1"], eco
    assert S.stable(["2.0.0-jre", "2.0.0-M1", "1.9"], "maven") == ["1.9", "2.0.0-jre"]  # maven keeps old rules: "-jre" is a release
    assert S.stable(["1.0a1", "1.0"], "pip") == ["1.0"]

if __name__ == "__main__":
    test(); print("ok")
