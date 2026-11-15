from lxml import etree


def parse(path):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return etree.parse(path, parser)
