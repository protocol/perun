"""Route registry: collects Starlette routes declared with decorators."""
from starlette.routing import Route


class Registry:
    def __init__(self, prefix=""):
        self.prefix, self.routes = prefix, []

    def add(self, path, methods):
        def deco(fn):
            self.routes.append(Route(path, fn, methods=methods))
            return fn

        return deco

    def get(self, path):
        return self.add(path, ["GET"])

    def post(self, path):
        return self.add(path, ["POST"])

    def put(self, path):
        return self.add(path, ["PUT"])

    def delete(self, path):
        return self.add(path, ["DELETE"])
