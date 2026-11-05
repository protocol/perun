const { exec } = require('child_process');
const axios = require('axios');

async function getPreset(name) {
  const res = await axios.get(`https://presets.example.com/v1/${encodeURIComponent(name)}`);
  return res.data;
}

async function convert(input, name) {
  const preset = await getPreset(name);
  return new Promise((resolve, reject) => {
    exec(`ffmpeg -i ${input} ${preset.flags} out.mp4`, (err, stdout) => {
      if (err) return reject(err);
      resolve(stdout);
    });
  });
}

module.exports = { convert };
