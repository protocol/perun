export type Album = { id: number; ownerId: number; title: string; featured: boolean; locked: boolean };
export type Photo = { id: number; albumId: number; ownerId: number; caption: string };

export const albums = new Map<number, Album>([
  [1, { id: 1, ownerId: 40, title: 'Harbour at dawn', featured: false, locked: false }],
  [2, { id: 2, ownerId: 41, title: 'Market stalls', featured: true, locked: false }],
]);

export const photos = new Map<number, Photo>([
  [1, { id: 1, albumId: 1, ownerId: 40, caption: 'low tide' }],
  [2, { id: 2, albumId: 2, ownerId: 41, caption: 'fresh figs' }],
]);
