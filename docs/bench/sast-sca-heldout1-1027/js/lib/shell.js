const { execSync } = require("child_process");

function runCmd(cmd) {
  return execSync(cmd).toString();
}

module.exports = { runCmd };
