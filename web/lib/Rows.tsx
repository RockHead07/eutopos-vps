/** Kerangka baris selama data pertama dimuat, pengganti teks "Loading...". */
export function Rows({ n = 3 }: { n?: number }) {
  return (
    <div className="rows" aria-label="Loading">
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skeleton row" />
      ))}
    </div>
  );
}
