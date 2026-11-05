const axios = require("axios");
const { exec } = require("child_process");
const { promisify } = require("util");

const run = promisify(exec);
const REGISTRY = "https://registry.acme-builds.example.com";

async function latestBundle(project) {
  const { data } = await axios.get(`${REGISTRY}/projects/${project}/latest`, {
    timeout: 8000,
  });
  return data;
}

async function unpack(project, dest) {
  const bundle = await latestBundle(project);
  const cmd = `tar -xf /srv/bundles/${bundle.archive_name} -C ${dest}`;
  const { stdout } = await run(cmd);
  return stdout;
}

async function main() {
  console.log(await unpack(process.argv[2], "/srv/work"));
}

main().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});
