const { execFile } = require('child_process');

const CODEC = /^[a-z0-9]{2,8}$/;

async function fetchProfile(id) {
  const res = await fetch(`https://profiles.example.com/v1/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('profile lookup failed');
  return res.json();
}

async function makeThumb(id, input) {
  const profile = await fetchProfile(id);
  if (!CODEC.test(profile.codec)) {
    throw new Error('codec rejected');
  }
  return new Promise((resolve, reject) => {
    execFile('acme-thumb', ['--codec', profile.codec, input], (err, out) => {
      if (err) return reject(err);
      resolve(out);
    });
  });
}

module.exports = { makeThumb };
