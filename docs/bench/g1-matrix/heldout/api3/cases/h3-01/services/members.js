const Member = require('../models/member');

async function getMember(id) {
  const member = await Member.findById(id).lean();
  if (!member) {
    const err = new Error('member not found');
    err.status = 404;
    throw err;
  }
  return member;
}

async function updateMember(id, patch) {
  await getMember(id);
  return Member.findOneAndUpdate(
    { _id: id },
    { $set: patch },
    { new: true }
  );
}

module.exports = { getMember, updateMember };
