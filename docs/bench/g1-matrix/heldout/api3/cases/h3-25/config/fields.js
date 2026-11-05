// Fields a member may change on their own record.
const EDITABLE = {
  member: ['displayName', 'avatarUrl', 'locale', 'newsletter'],
  team: ['title', 'description'],
  project: ['name', 'summary', 'archived'],
  comment: ['text'],
  invite: ['message'],
  badge: ['label'],
};

module.exports = { EDITABLE };

// Keep this list in step with the member schema when columns are added,
// and review additions together with the access rules for the new column.
// Each entry is a plain property name, with no nested paths.
