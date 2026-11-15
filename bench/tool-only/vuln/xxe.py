from lxml import etree


def parse(path):
    parser = etree.XMLParser(resolve_entities=True, no_network=False)
    return etree.parse(path, parser)
