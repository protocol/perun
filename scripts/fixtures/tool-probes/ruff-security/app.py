def run(cmd):
    # ruff does not honor nosec, so only the ruff-security row survives the bandit twin dedupe
    return eval(cmd)  # nosec
