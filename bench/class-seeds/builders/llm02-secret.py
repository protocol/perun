"""Builds an LLM02 (sensitive information disclosure) seed: a hard-coded credential for gitleaks.
The token is assembled from split parts at test time so no fake secret sits in the repo."""
import os


def build(dst, kind):
    if kind == "clean":
        body = 'import os\n\nTOKEN = os.environ["ACME_GH_TOKEN"]  # injected at runtime, never committed\n'
        name = "settings.py"
    elif kind == "mutant":
        tok = "sk" + "_live_" + "4eC39HqLyjWDarjtT1zdp7dc" + "Xa9Zk2Qm"
        body = 'module.exports = {\n  payments: { key: "%s" },\n};\n' % tok
        name = "config.js"
    else:
        tok = "gh" + "p_" + "Zq7Lm2Xv9Rk4Tn8Bw3Yc6Hd1Fg5Js0Pa" + "Ue2N"
        body = 'GITHUB_TOKEN = "%s"\n\n\ndef headers():\n    return {"Authorization": "token " + GITHUB_TOKEN}\n' % tok
        name = "settings.py"
    with open(os.path.join(dst, name), "w") as f:
        f.write(body)
