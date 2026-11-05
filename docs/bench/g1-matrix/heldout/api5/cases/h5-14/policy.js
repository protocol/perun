const table = {
  support: ['invoice:set-status'],
  owner: ['invoice:set-status', 'invoice:refund'],
};

function can(user, action) {
  const allowed = table[user.group] || [];
  return allowed.includes(action);
}

module.exports = { can };
