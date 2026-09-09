import type { Photo } from "@/data/photos";

// 鬼刀背景图 · 图床 CDN 链接（见 F:\AI\projects\fastimage\鬼刀图床链接.md）
// 图床仓库：neutron-star77/fastimage（GitHub + jsDelivr，public），共 234 张，长边 1920 / webp q82
const BASE = "https://cdn.jsdelivr.net/gh/neutron-star77/fastimage@main/2026/08/";
const FIRST = 433;
const LAST = 666; // 234 张

export interface GuidaoAlbum {
  id: number;
  title: string;
  updatedAt: string;
  photoCount: number;
  photos: Photo[];
}

export const guidaoAlbum: GuidaoAlbum = {
  id: 1,
  title: "鬼刀图集",
  updatedAt: "2026-08-01T00:00:00",
  photoCount: LAST - FIRST + 1,
  photos: Array.from({ length: LAST - FIRST + 1 }, (_, i) => {
    const n = FIRST + i;
    return {
      id: String(n),
      url: `${BASE}${n}.webp`,
      caption: `鬼刀 #${i + 1}`,
      orientation: "portrait" as const,
    };
  }),
};
