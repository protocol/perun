const { exec } = require("child_process");

async function getRepo(name) {
  const res = await fetch(`https://git.example.com/api/repos/${name}`);
  if (!res.ok) throw new Error("lookup failed");
  return res.json();
}

function sh(cmd) {
  return new Promise((resolve, reject) => {
    exec(cmd, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

async function checkout(name) {
  const repo = await getRepo(name);
  return sh(`git clone ${repo.clone_url} /srv/acme/work/${name}`);
}

module.exports = { checkout };
