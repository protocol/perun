import subprocess


def run(cmd):
    subprocess.call(cmd, shell=True)
    return eval(cmd)
