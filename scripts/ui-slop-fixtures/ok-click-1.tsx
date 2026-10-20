export const Row = ({ go }: { go: () => void }) => (
  <div role="button" tabIndex={0} onClick={go}>Open</div>
);
export const B = ({ go }: { go: () => void }) => <button onClick={go}>Save</button>;
