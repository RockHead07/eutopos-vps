import NextLink from "next/link";
import type { ComponentProps } from "react";

// ponytail: prefetch dimatikan untuk semua tautan. Next 16.3.8 (static export) mem-prefetch
// /<rute>/__next.<rute>.__PAGE__.txt, padahal berkasnya ditulis di /<rute>/__next.<rute>/__PAGE__.txt,
// jadi setiap prefetch 404. Halaman kecil dan datanya diambil di klien, jadi tidak ada yang hilang.
// Hapus pembungkus ini kalau Next memperbaiki jalurnya.
export default function Link(props: ComponentProps<typeof NextLink>) {
  return <NextLink prefetch={false} {...props} />;
}
