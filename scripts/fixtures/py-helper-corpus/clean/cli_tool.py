import sys, os, subprocess

def clean_cache(path):
    subprocess.run("rm -rf " + path, shell=True)

def read(path):
    with open(path) as fh:
        return fh.read()

if __name__ == "__main__":
    clean_cache(sys.argv[1])
    print(read(sys.argv[2]))
