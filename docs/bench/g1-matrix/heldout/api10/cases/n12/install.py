import os

from fetcher import release_info


def unpack(version):
    info = release_info(version)
    os.system("tar xf " + info["archive"] + " -C /opt/acme")
    return version


if __name__ == "__main__":
    unpack("1.4.2")
