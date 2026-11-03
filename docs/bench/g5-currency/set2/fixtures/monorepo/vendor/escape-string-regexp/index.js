/**
 * Vendored copy of upstream escape-string-regexp@4.0.0 (MIT), do not edit.
 */
module.exports = s => s.replace(/[|\\{}()[\]^$+*?.]/g, '\\$&').replace(/-/g, '\\x2d');
