const { execFile } = require("child_process");

const ORIGIN = /^https:\/\/git\.example\.com\/[a-z0-9_-]+\/[a-z0-9_-]+\.git$/;

async function getRepo(name) {
  const res = await fetch(`https://git.example.com/api/repos/${name}`);
  if (!res.ok) throw new Error("lookup failed");
  return res.json();
}

function run(file, args) {
  return new Promise((resolve, reject) => {
    execFile(file, args, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

async function checkout(name) {
  const repo = await getRepo(name);
  if (!ORIGIN.test(repo.clone_url)) {
    throw new Error("unexpected remote");
  }
  return run("git", ["clone", "--", repo.clone_url, `/srv/acme/work/${name}`]);
}

module.exports = { checkout };
