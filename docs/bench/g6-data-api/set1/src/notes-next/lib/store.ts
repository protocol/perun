export type Project = { id: number; ownerId: number; name: string; notes: string };
export type Task = { id: number; ownerId: number; title: string };

export const tokens: Record<string, { userId: number; role: string }> = {
  'tok-member': { userId: 50, role: 'member' },
  'tok-admin': { userId: 51, role: 'admin' },
};

export const projects = new Map<number, Project>([
  [1, { id: 1, ownerId: 50, name: 'Site refresh', notes: 'budget tbd' }],
  [2, { id: 2, ownerId: 51, name: 'Audit prep', notes: 'confidential' }],
]);

export const tasks = new Map<number, Task>([
  [1, { id: 1, ownerId: 50, title: 'Draft copy' }],
  [2, { id: 2, ownerId: 51, title: 'Collect evidence' }],
]);

export const flags: Record<string, boolean> = { beta_editor: false, share_links: true };
