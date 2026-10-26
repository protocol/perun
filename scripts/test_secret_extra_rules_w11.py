#!/usr/bin/env python3
"""Regression pins for secrets wave 11 (held-out-14 blind): nuget ClearTextPassword, Azure SAS with sig first, client-secret assignments, Stripe whsec_,
Sentry sntrys_/sntryu_ without eyJ, Doppler dp.st tokens, echo-piped `login --password-stdin`; plus three decoy fixes (a referrer-restricted web key,
a passwordResetUrl, an sk-test- fixture). Tokens built at runtime. Offline.
"""
import hashlib, importlib.util, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ss", ROOT / "scripts/secret_scan.py")
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
AN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def tok(seed, n, alpha=AN):
    """Deterministic high-entropy string of length n over alpha."""
    return "".join(alpha[b % len(alpha)] for b in hashlib.sha256(seed.encode()).digest() * 8)[:n]


def ids(text):
    return ss.gitleaks_rule(text + "\n", "x.txt", True)


LIVE = {
    "nuget-cleartext-password": ['<add key="ClearTextPassword" value="' + "".join(c for c in tok("a", 40) if c.isalpha())[:25] + '" />'],
    "sas-sig-first": ["sig=" + tok("b", 43) + "%3D&se=2027-01-01&sp=rwdl&sv=2022-11-02", "?sig=" + tok("c", 44) + "&sp=r&sv=2022-11-02"],
    "client-secret-assign": ["AZURE_CLIENT_" "SECRET: " + tok("d", 40), "client_secret = '" + tok("e", 36) + "'"],
    "stripe-webhook-secret": ["wh" "sec_" + tok("f", 32), "STRIPE_ENDPOINT=wh" "sec_" + tok("g", 40)],
    "sentry-org-token": ["SENTRY_AUTH_TOKEN=sntry" "s_" + tok("h", 72, AN + "+/"), "token: sntry" "u_" + tok("i", 64, "0123456789abcdef")],
    "doppler-token": ["DOPPLER_TOKEN=dp" ".st.dev." + tok("j", 40), "dp" ".pt." + tok("k", 44), "dp" ".sa." + tok("l", 40)],
    "piped-login-password": ['echo "' + tok("m", 40) + '" | docker login ghcr.io -u jane --password-stdin', "printf " + tok("n", 30) + " | podman login quay.io -u jane --password-stdin"],
}
DECOY = [
    '<add key="ClearTextPassword" value="${NUGET_PASS}" />', '<add key="ClearTextPassword" value="short" />',
    "sig=" + tok("o", 43) + "%3D", "sig=short&se=2027", "AZURE_CLIENT_SECRET: ${AZURE_CLIENT_SECRET}", "client_secret = " + "settings.client_secret_value", "client_secret: abc",
    "wh" "sec_${STRIPE_WEBHOOK}", "wh" "sec_short", "whsec_<your-secret>",
    "sntry" "s_short", "dp" ".st.dev.${DOPPLER_TOKEN}", "dp" ".st.dev.short", 'echo "$GH_TOKEN" | docker login ghcr.io -u jane --password-stdin',
    'echo "${{ secrets.TOKEN }}" | docker login -u jane --password-stdin', "echo hello | docker login",
    "FIREBASE_WEB_API_KEY=AIza" + tok("q", 35) + "  # web key, restricted by referrer", "passwordResetUrl: https://example.com/reset?id=" + tok("r", 12),
    "sk-test-" + tok("s", 20) + "  # fixture literal in docs",
]
bad = [("miss", r, t) for r, ts in LIVE.items() for t in ts if r not in ids(t)] + [("fp", t) for t in DECOY if ids(t)]
assert not bad, bad
# review fixes: bypasses that must flag, near-misses that must pass
HEX = "0123456789abcdef"
LIVE2 = ["?se=2027-01-01&sp=r&sig=" + tok("r1", 43) + "%3D", "sv=2022-11-02&se=2027-01-01&sp=r&sr=b&sig=" + tok("r2", 44), "printf '%s' " + tok("r3", 40) + " | docker login ghcr.io -u jane --password-stdin",
         "echo -e " + tok("r4", 40) + " | docker login -u jane --password-stdin", "cat <<< " + tok("r5", 40) + " | docker login -u jane --password-stdin", "docker login -u jane --password-stdin <<< " + tok("r6", 40),
         "echo " + tok("r7", 40) + " | tee x | docker login -u jane --password-stdin", "echo " + tok("r8", 40) + " | gh auth login --with-token", "DOPPLER_TOKEN=dp" ".st.Dev." + tok("r9", 40),
         "dp" ".st.prod.eu_west." + tok("ra", 40), "DD_API_" "KEY: " + "".join(HEX[b % 16] for b in hashlib.sha256(b"r").digest())[:34],
         "<add value=\"" + "".join(c for c in tok("rb", 60) if c.isalpha())[:25] + "\" key=\"ClearText" "Password\" />", "<add key='ClearText" "Password' value = '" + "".join(c for c in tok("rc", 60) if c.isalpha())[:25] + "'/>",
         "API_KEY=" + tok("rd", 40) + " # not restricted to referrer", "token=\"" + tok("re", 40) + "\" -- referrer-restricted", "DESK_TEST_API_KEY=" + tok("rf", 40),
         "password_curl=" + tok("rh", 12) + "!047"]
DECOY2 = ["client_secret_name=MyClientSecretValueIsLongEnough123456", "client_secret_path: /run/secrets/" + tok("s1", 36), "clientSecretExpiry: 2027-01-01T00:00:00Z-" + tok("s3", 20),
          "client_secret=@Microsoft.KeyVault(SecretUri=https://v.example.com/secrets/s/" + tok("s5", 12) + ")", "client_secret: ENC[AES256_GCM,data:" + tok("s6", 40) + "]",
          "echo \"foo-bar-baz-qux-version-2-release-build\" | docker login --password-stdin", "printf '%s' \"$TOKEN\" | docker login --password-stdin", "passwordResetUrl: https://example.com/reset?id=" + tok("s7", 12),
          "password_url: https://example.com/p?id=" + tok("s8", 12)]
bad = [("miss", t) for t in LIVE2 if not ids(t)] + [("fp", t) for t in DECOY2 if ids(t)]
assert not bad, bad
# review 2: negated referrer comments, printf format with \n, UUID tokens, client_secret metadata names
LIVE3 = ["API_KEY=AIza" + tok("t1", 35) + "  # not restricted to referrer", "API_KEY=AIza" + tok("t2", 35) + "  # un-restricted public key", "API_KEY=AIza" + tok("t3", 35) + "  // unrestricted",
         "printf '%s\\n' " + tok("t4", 40) + " | docker login ghcr.io -u jane --password-stdin", "echo " + "-".join(tok("u" + str(i), n, HEX) for i, n in enumerate((8, 4, 4, 4, 12))) + " | docker login --password-stdin",
         "echo " + "-".join(tok("v" + str(i), 4) for i in range(6)) + " | docker login --password-stdin", "AZURE_CLIENT_SECRET_VALUE=" + tok("t5", 40)]
DECOY3 = ["client_secret_" + n + ": " + tok("t6", 40) for n in ("type", "id", "version", "expires_at", "basic", "ref")]
bad = [("miss", t) for t in LIVE3 if not ids(t)] + [("fp", t) for t in DECOY3 if ids(t)]
assert not bad, bad
print("secret extra rules w11: ok")
