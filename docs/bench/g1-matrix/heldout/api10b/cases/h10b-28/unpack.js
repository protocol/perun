const axios = require("axios");
const { execFile } = require("child_process");
const { promisify } = require("util");

const run = promisify(execFile);
const REGISTRY = "https://registry.acme-builds.example.com";
const NAME = /^[a-z0-9][a-z0-9._-]{0,63}\.tar$/;

async function latestBundle(project) {
  const { data } = await axios.get(`${REGISTRY}/projects/${project}/latest`, {
    timeout: 8000,
  });
  return data;
}

async function unpack(project, dest) {
  const bundle = await latestBundle(project);
  if (!NAME.test(bundle.archive_name)) {
    throw new Error("unexpected archive name");
  }
  const { stdout } = await run("tar", [
    "-xf",
    `/srv/bundles/${bundle.archive_name}`,
    "-C",
    dest,
  ]);
  return stdout;
}

module.exports = { unpack };
