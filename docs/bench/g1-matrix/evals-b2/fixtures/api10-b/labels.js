const fs = require('fs/promises');
const path = require('path');

const LABEL_DIR = path.join(__dirname, 'labels');

async function saveLabel(shipment) {
  if (!shipment.labelName || !shipment.labelBase64) return null;
  const bytes = Buffer.from(shipment.labelBase64, 'base64');
  if (bytes.length > 512 * 1024) throw new Error('label too large');
  const target = path.join(LABEL_DIR, shipment.labelName);
  await fs.mkdir(LABEL_DIR, { recursive: true });
  await fs.writeFile(target, bytes);
  return target;
}

async function readLabel(name) {
  return fs.readFile(path.join(LABEL_DIR, path.basename(name)));
}

module.exports = { saveLabel, readLabel };
